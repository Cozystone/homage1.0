//! Protocol handlers — kiosk policy, not window policy.
//!
//! Where a window manager would honor move/resize grabs and let clients pick
//! their own size, the ATANOR surface does the opposite: every toplevel is
//! configured to fill the output and receives keyboard focus the moment its
//! first commit lands. There is nothing to drag because there are no windows.

use smithay::{
    backend::renderer::utils::on_commit_buffer_handler,
    delegate_compositor, delegate_data_device, delegate_output, delegate_seat, delegate_shm,
    delegate_xdg_shell,
    desktop::{find_popup_root_surface, get_popup_toplevel_coords, PopupKind, Window},
    input::{Seat, SeatHandler, SeatState},
    reexports::{
        wayland_protocols::xdg::shell::server::xdg_toplevel,
        wayland_server::{
            protocol::{wl_buffer, wl_seat, wl_surface::WlSurface},
            Client, Resource,
        },
    },
    utils::{Serial, SERIAL_COUNTER},
    wayland::{
        buffer::BufferHandler,
        compositor::{
            get_parent, is_sync_subsurface, with_states, CompositorClientState, CompositorHandler,
            CompositorState,
        },
        output::OutputHandler,
        selection::data_device::{
            set_data_device_focus, ClientDndGrabHandler, DataDeviceHandler, DataDeviceState,
            ServerDndGrabHandler,
        },
        selection::SelectionHandler,
        shell::xdg::{
            PopupSurface, PositionerState, ToplevelSurface, XdgShellHandler, XdgShellState,
            XdgToplevelSurfaceData,
        },
        shm::{ShmHandler, ShmState},
    },
};

use crate::state::{AtanorShell, ClientState};

// ---------------------------------------------------------------- compositor

impl CompositorHandler for AtanorShell {
    fn compositor_state(&mut self) -> &mut CompositorState {
        &mut self.compositor_state
    }

    fn client_compositor_state<'a>(&self, client: &'a Client) -> &'a CompositorClientState {
        &client.get_data::<ClientState>().unwrap().compositor_state
    }

    fn commit(&mut self, surface: &WlSurface) {
        on_commit_buffer_handler::<Self>(surface);
        if !is_sync_subsurface(surface) {
            let mut root = surface.clone();
            while let Some(parent) = get_parent(&root) {
                root = parent;
            }
            if let Some(window) = self
                .space
                .elements()
                .find(|w| w.toplevel().map(|t| t.wl_surface() == &root).unwrap_or(false))
            {
                window.on_commit();
            }
        }

        self.handle_toplevel_commit(surface);
        self.handle_popup_commit(surface);
    }
}

impl BufferHandler for AtanorShell {
    fn buffer_destroyed(&mut self, _buffer: &wl_buffer::WlBuffer) {}
}

impl ShmHandler for AtanorShell {
    fn shm_state(&self) -> &ShmState {
        &self.shm_state
    }
}

delegate_compositor!(AtanorShell);
delegate_shm!(AtanorShell);

// ----------------------------------------------------------------- xdg-shell

impl XdgShellHandler for AtanorShell {
    fn xdg_shell_state(&mut self) -> &mut XdgShellState {
        &mut self.xdg_shell_state
    }

    fn new_toplevel(&mut self, surface: ToplevelSurface) {
        // Kiosk: the surface IS the screen. Configure to the full output
        // before the client's first commit so it never flashes at own-size.
        if let Some(output) = self.space.outputs().next() {
            if let Some(geo) = self.space.output_geometry(output) {
                surface.with_pending_state(|state| {
                    state.size = Some(geo.size);
                    state.states.set(xdg_toplevel::State::Activated);
                    state.states.set(xdg_toplevel::State::Maximized);
                });
            }
        }
        let window = Window::new_wayland_window(surface);
        self.space.map_element(window, (0, 0), true);
        tracing::info!("toplevel mapped (kiosk-sized)");
    }

    fn new_popup(&mut self, surface: PopupSurface, _positioner: PositionerState) {
        self.unconstrain_popup(&surface);
        let _ = self.popups.track_popup(PopupKind::Xdg(surface));
    }

    fn reposition_request(&mut self, surface: PopupSurface, positioner: PositionerState, token: u32) {
        surface.with_pending_state(|state| {
            let geometry = positioner.get_geometry();
            state.geometry = geometry;
            state.positioner = positioner;
        });
        self.unconstrain_popup(&surface);
        surface.send_repositioned(token);
    }

    fn move_request(&mut self, _surface: ToplevelSurface, _seat: wl_seat::WlSeat, _serial: Serial) {
        // No windows, nothing to move.
    }

    fn resize_request(
        &mut self,
        _surface: ToplevelSurface,
        _seat: wl_seat::WlSeat,
        _serial: Serial,
        _edges: xdg_toplevel::ResizeEdge,
    ) {
        // No windows, nothing to resize.
    }

    fn grab(&mut self, _surface: PopupSurface, _seat: wl_seat::WlSeat, _serial: Serial) {}
}

delegate_xdg_shell!(AtanorShell);

impl AtanorShell {
    /// First commit: send the initial configure, then hand the keyboard to
    /// the surface — the kiosk client must be typable without a click.
    fn handle_toplevel_commit(&mut self, surface: &WlSurface) {
        let Some(window) = self
            .space
            .elements()
            .find(|w| {
                w.toplevel()
                    .map(|t| t.wl_surface() == surface)
                    .unwrap_or(false)
            })
            .cloned()
        else {
            return;
        };

        let initial_configure_sent = with_states(surface, |states| {
            states
                .data_map
                .get::<XdgToplevelSurfaceData>()
                .unwrap()
                .lock()
                .unwrap()
                .initial_configure_sent
        });

        if !initial_configure_sent {
            if let Some(toplevel) = window.toplevel() {
                toplevel.send_configure();
            }
        } else if let Some(keyboard) = self.seat.get_keyboard() {
            if keyboard.current_focus().is_none() {
                keyboard.set_focus(self, Some(surface.clone()), SERIAL_COUNTER.next_serial());
                tracing::info!("keyboard focus -> kiosk surface");
            }
        }
    }

    fn handle_popup_commit(&mut self, surface: &WlSurface) {
        self.popups.commit(surface);
        if let Some(PopupKind::Xdg(ref xdg)) = self.popups.find_popup(surface) {
            if !xdg.is_initial_configure_sent() {
                xdg.send_configure().expect("initial popup configure");
            }
        }
    }

    fn unconstrain_popup(&self, popup: &PopupSurface) {
        let Ok(root) = find_popup_root_surface(&PopupKind::Xdg(popup.clone())) else {
            return;
        };
        let Some(window) = self
            .space
            .elements()
            .find(|w| w.toplevel().map(|t| t.wl_surface() == &root).unwrap_or(false))
        else {
            return;
        };
        let Some(output) = self.space.outputs().next() else {
            return;
        };
        let Some(output_geo) = self.space.output_geometry(output) else {
            return;
        };
        let Some(window_geo) = self.space.element_geometry(window) else {
            return;
        };

        let mut target = output_geo;
        target.loc -= get_popup_toplevel_coords(&PopupKind::Xdg(popup.clone()));
        target.loc -= window_geo.loc;

        popup.with_pending_state(|state| {
            state.geometry = state.positioner.get_unconstrained_geometry(target);
        });
    }
}

// ---------------------------------------------------------------------- seat

impl SeatHandler for AtanorShell {
    type KeyboardFocus = WlSurface;
    type PointerFocus = WlSurface;
    type TouchFocus = WlSurface;

    fn seat_state(&mut self) -> &mut SeatState<AtanorShell> {
        &mut self.seat_state
    }

    fn cursor_image(&mut self, _seat: &Seat<Self>, _image: smithay::input::pointer::CursorImageStatus) {}

    fn focus_changed(&mut self, seat: &Seat<Self>, focused: Option<&WlSurface>) {
        let dh = &self.display_handle;
        let client = focused.and_then(|s| dh.get_client(s.id()).ok());
        set_data_device_focus(dh, seat, client);
    }
}

delegate_seat!(AtanorShell);

// --------------------------------------------------------------- data device

impl SelectionHandler for AtanorShell {
    type SelectionUserData = ();
}

impl DataDeviceHandler for AtanorShell {
    fn data_device_state(&self) -> &DataDeviceState {
        &self.data_device_state
    }
}

impl ClientDndGrabHandler for AtanorShell {}
impl ServerDndGrabHandler for AtanorShell {}

delegate_data_device!(AtanorShell);

// -------------------------------------------------------------------- output

impl OutputHandler for AtanorShell {}
delegate_output!(AtanorShell);
