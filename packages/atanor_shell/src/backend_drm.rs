//! DRM/TTY backend — M1b: atanor-shell owns the metal. No cage, no X, no
//! browser: the kernel hands us the display (KMS) and input (libinput via
//! libseat), and everything above state.rs stays byte-identical.
//!
//! Software path by design: the ATANOR Linux VM (virtio-vga, no GL) renders
//! through pixman into dumb buffers; the DrmCompositor exports each dumb
//! buffer as a dmabuf and the pixman renderer binds that. On GL hardware this
//! file later grows a gles branch — the layers above never notice.
//!
//! v1 honesty: no cursor plane (kiosk is keyboard-first), no VT-switch chord,
//! session pause/resume is logged but not replayed (a kiosk VM never switches
//! VTs; revisit for metal laptops).

use std::{cell::RefCell, path::Path, rc::Rc, time::Duration};

use smithay::{
    backend::{
        allocator::{dumb::DumbAllocator, Format as DrmFormat, Fourcc, Modifier},
        drm::{
            compositor::{DrmCompositor, FrameFlags},
            DrmDevice, DrmDeviceFd, DrmEvent,
        },
        libinput::{LibinputInputBackend, LibinputSessionInterface},
        renderer::{
            element::{
                memory::MemoryRenderBufferRenderElement, surface::WaylandSurfaceRenderElement,
                AsRenderElements, Kind,
            },
            pixman::PixmanRenderer,
            ImportAll, ImportMem,
        },
        session::{libseat::LibSeatSession, Event as SessionEvent, Session},
    },
    output::{Mode, Output, PhysicalProperties, Subpixel},
    reexports::{
        calloop::{
            timer::{TimeoutAction, Timer},
            EventLoop, LoopHandle,
        },
        drm::control::{connector::State as ConnectorState, Device as ControlDevice, ModeTypeFlags},
        gbm::Device as GbmDevice,
        input::Libinput,
        rustix::fs::OFlags,
    },
    utils::{DeviceFd, Scale, Transform},
};

use crate::{field::ParticleField, AtanorShell, CalloopData};

const DEEP_SPACE: [f32; 4] = [0.0196, 0.0275, 0.0392, 1.0];

type KioskCompositor = DrmCompositor<DumbAllocator, DrmDeviceFd, (), DrmDeviceFd>;

smithay::render_elements! {
    // layer 0 is OURS: clients composite over the native particle field
    pub KioskFrame<R> where R: ImportAll + ImportMem;
    Window=WaylandSurfaceRenderElement<R>,
    Field=MemoryRenderBufferRenderElement<R>,
}

struct DrmRender {
    compositor: KioskCompositor,
    renderer: PixmanRenderer,
    output: Output,
    field: ParticleField,
    queued: bool,
}

pub fn init_drm(
    event_loop: &mut EventLoop<'static, CalloopData>,
    data: &mut CalloopData,
) -> Result<(), Box<dyn std::error::Error>> {
    let display_handle = data.display_handle.clone();
    let loop_handle = event_loop.handle();

    // --- session: the seat gives us device access without being root
    let (mut session, notifier) = LibSeatSession::new()?;
    let seat_name = session.seat();
    tracing::info!(seat = %seat_name, "libseat session up");

    // --- input: libinput on the seat, feeding the backend-agnostic router
    let mut libinput_context =
        Libinput::new_with_udev::<LibinputSessionInterface<LibSeatSession>>(session.clone().into());
    libinput_context
        .udev_assign_seat(&seat_name)
        .map_err(|_| "udev_assign_seat failed")?;
    let libinput_backend = LibinputInputBackend::new(libinput_context.clone());
    loop_handle
        .insert_source(libinput_backend, |event, _, data| {
            data.state.process_input_event(event);
        })
        .map_err(|e| format!("libinput source: {e}"))?;

    loop_handle
        .insert_source(notifier, |event, _, _data| match event {
            SessionEvent::PauseSession => tracing::warn!("session paused (VT switch?)"),
            SessionEvent::ActivateSession => tracing::warn!("session resumed"),
        })
        .map_err(|e| format!("session source: {e}"))?;

    // --- the GPU (or the VM's virtio display): first card, opened via the session
    let fd = session.open(
        Path::new("/dev/dri/card0"),
        OFlags::RDWR | OFlags::CLOEXEC | OFlags::NOCTTY | OFlags::NONBLOCK,
    )?;
    let device_fd = DrmDeviceFd::new(DeviceFd::from(fd));
    let (mut drm, drm_notifier) = DrmDevice::new(device_fd.clone(), true)?;

    // --- connector scan: first connected connector, preferred mode
    let res_handles = drm.resource_handles()?;
    let connector = res_handles
        .connectors()
        .iter()
        .filter_map(|c| drm.get_connector(*c, true).ok())
        .find(|c| c.state() == ConnectorState::Connected)
        .ok_or("no connected connector")?;
    let mode = *connector
        .modes()
        .iter()
        .find(|m| m.mode_type().contains(ModeTypeFlags::PREFERRED))
        .unwrap_or(&connector.modes()[0]);
    let encoder = connector
        .encoders()
        .iter()
        .filter_map(|e| drm.get_encoder(*e).ok())
        .next()
        .ok_or("no encoder")?;
    let crtc = encoder
        .crtc()
        .or_else(|| res_handles.filter_crtcs(encoder.possible_crtcs()).first().copied())
        .ok_or("no crtc")?;
    let (w, h) = (mode.size().0 as i32, mode.size().1 as i32);
    tracing::info!("drm mode {}x{} @connector {:?}", w, h, connector.interface());

    let surface = drm.create_surface(crtc, mode, &[connector.handle()])?;

    // --- the output the space maps windows onto
    let output = Output::new(
        "atanor-drm".to_string(),
        PhysicalProperties {
            size: (0, 0).into(),
            subpixel: Subpixel::Unknown,
            make: "ATANOR".into(),
            model: "Shell M1b".into(),
        },
    );
    let _global = output.create_global::<AtanorShell>(&display_handle);
    let out_mode = Mode {
        size: (w, h).into(),
        refresh: (mode.vrefresh() * 1000) as i32,
    };
    output.change_current_state(Some(out_mode), Some(Transform::Normal), None, Some((0, 0).into()));
    output.set_preferred(out_mode);
    data.state.space.map_output(&output, (0, 0));

    // --- software swapchain: dumb buffers, exported per-frame as dmabufs
    let allocator = DumbAllocator::new(device_fd.clone());
    let renderer = PixmanRenderer::new()?;
    let compositor: KioskCompositor = DrmCompositor::new(
        &output,
        surface,
        None,
        allocator,
        device_fd.clone(),
        [Fourcc::Xrgb8888],
        [
            DrmFormat { code: Fourcc::Xrgb8888, modifier: Modifier::Linear },
            DrmFormat { code: Fourcc::Xrgb8888, modifier: Modifier::Invalid },
        ],
        drm.cursor_size(),
        None::<GbmDevice<DrmDeviceFd>>,
    )?;

    let render = Rc::new(RefCell::new(DrmRender {
        compositor,
        renderer,
        output,
        field: ParticleField::new(w, h, 3200),
        queued: false,
    }));

    // --- vblank: the pageflip completed; draw the next frame
    let render_vblank = render.clone();
    let loop_vblank = loop_handle.clone();
    loop_handle
        .insert_source(drm_notifier, move |event, _, data| {
            if let DrmEvent::VBlank(_crtc) = event {
                {
                    let mut r = render_vblank.borrow_mut();
                    let _ = r.compositor.frame_submitted();
                    r.queued = false;
                }
                render_frame(&render_vblank, &loop_vblank, data);
            }
        })
        .map_err(|e| format!("drm source: {e}"))?;

    // --- first frame
    let render_first = render.clone();
    let loop_first = loop_handle.clone();
    loop_handle
        .insert_source(Timer::immediate(), move |_, _, data| {
            render_frame(&render_first, &loop_first, data);
            TimeoutAction::Drop
        })
        .map_err(|e| format!("first-frame timer: {e}"))?;

    tracing::info!("ATANOR Shell M1b up — DRM/pixman, we own the metal");
    Ok(())
}

/// Render the space through pixman into the drm swapchain. When nothing
/// changed (empty frame) we poll again next tick instead of queueing —
/// queue_frame on an empty frame is an error, not a no-op.
fn render_frame(render: &Rc<RefCell<DrmRender>>, loop_handle: &LoopHandle<'static, CalloopData>, data: &mut CalloopData) {
    {
        let r = &mut *render.borrow_mut();
        if r.queued {
            return;
        }
        r.field.step(1.0 / 60.0);
        r.field.rasterize();
        let mut elements: Vec<KioskFrame<PixmanRenderer>> = Vec::new();
        let windows: Vec<_> = data.state.space.elements().cloned().collect();
        for window in windows.iter().rev() {
            if let Some(loc) = data.state.space.element_location(window) {
                let loc = loc.to_physical_precise_round(1.0);
                elements.extend(window.render_elements::<KioskFrame<PixmanRenderer>>(
                    &mut r.renderer,
                    loc,
                    Scale::from(1.0),
                    1.0,
                ));
            }
        }
        match MemoryRenderBufferRenderElement::from_buffer(
            &mut r.renderer,
            (0.0, 0.0),
            &r.field.buffer,
            None,
            None,
            None,
            Kind::Unspecified,
        ) {
            Ok(el) => elements.push(KioskFrame::Field(el)),
            Err(err) => tracing::warn!("field element: {err}"),
        }
        match r
            .compositor
            .render_frame(&mut r.renderer, &elements, DEEP_SPACE, FrameFlags::DEFAULT)
        {
            Ok(result) => {
                if !result.is_empty {
                    match r.compositor.queue_frame(()) {
                        Ok(()) => r.queued = true,
                        Err(err) => tracing::warn!("queue_frame: {err}"),
                    }
                }
            }
            Err(err) => {
                tracing::warn!("render_frame: {err}");
                r.compositor.reset_buffers();
            }
        }
        if !r.queued {
            // idle: check again next tick (a commit may arrive any time)
            let render_retry = render.clone();
            let loop_retry = loop_handle.clone();
            let _ = loop_handle.insert_source(
                Timer::from_duration(Duration::from_millis(16)),
                move |_, _, data| {
                    render_frame(&render_retry, &loop_retry, data);
                    TimeoutAction::Drop
                },
            );
        }
        let output = r.output.clone();
        data.state.space.elements().for_each(|window| {
            window.send_frame(&output, data.state.start_time.elapsed(), Some(Duration::ZERO), |_, _| {
                Some(output.clone())
            })
        });
    }
    data.state.space.refresh();
    data.state.popups.cleanup();
    let _ = data.display_handle.flush_clients();
}
