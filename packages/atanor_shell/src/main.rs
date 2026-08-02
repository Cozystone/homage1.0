//! ATANOR Shell — M1: a real compositor.
//!
//! M0 proved we can put pixels on screen; M1 proves we can BE the screen:
//! atanor-shell now speaks wayland (compositor/xdg-shell/shm/seat/output),
//! hosts an actual client, and applies the kiosk policy the post-window
//! surface needs. Run it, and WAYLAND_DISPLAY points at *us*.
//!
//!   atanor-shell                 # hosts weston-terminal as a smoke client
//!   atanor-shell -c 'wayland-info'  # any command, spawned onto our socket
//!
//! M1b: DRM/TTY + libinput backend (boot ATANOR Linux straight into this).
//! M2: native SPLATRA point-sprite field as the layer-0 background.

mod backend_drm;
mod field;
mod backend_winit;
mod handlers;
mod input;
mod state;

use smithay::reexports::{
    calloop::EventLoop,
    wayland_server::{Display, DisplayHandle},
};
pub use state::AtanorShell;

pub struct CalloopData {
    state: AtanorShell,
    display_handle: DisplayHandle,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    if let Ok(env_filter) = tracing_subscriber::EnvFilter::try_from_default_env() {
        tracing_subscriber::fmt().with_env_filter(env_filter).init();
    } else {
        tracing_subscriber::fmt().init();
    }

    let mut event_loop: EventLoop<'static, CalloopData> = EventLoop::try_new()?;

    let display: Display<AtanorShell> = Display::new()?;
    let display_handle = display.handle();
    let state = AtanorShell::new(&mut event_loop, display);
    let socket_name = state.socket_name.clone();

    let mut data = CalloopData {
        state,
        display_handle,
    };

    // Backend choice: on the metal (a TTY, no host compositor) take DRM;
    // nested (WSLg/cage dev loop) take winit. ATANOR_BACKEND overrides.
    let on_metal = std::env::var("WAYLAND_DISPLAY").is_err()
        && std::env::var("DISPLAY").is_err()
        && std::path::Path::new("/dev/dri/card0").exists();
    match std::env::var("ATANOR_BACKEND").as_deref() {
        Ok("drm") => backend_drm::init_drm(&mut event_loop, &mut data)?,
        Ok("winit") => backend_winit::init_winit(&mut event_loop, &mut data)?,
        _ if on_metal => backend_drm::init_drm(&mut event_loop, &mut data)?,
        _ => backend_winit::init_winit(&mut event_loop, &mut data)?,
    }

    tracing::info!(?socket_name, "ATANOR Shell up — we are the compositor");

    // Children inherit OUR socket, nothing else's.
    let mut args = std::env::args().skip(1);
    let command = match (args.next().as_deref(), args.next()) {
        (Some("-c") | Some("--command"), Some(cmd)) => cmd,
        _ => "weston-terminal".to_string(),
    };
    std::process::Command::new("sh")
        .arg("-c")
        .arg(&command)
        .env("WAYLAND_DISPLAY", &socket_name)
        .spawn()
        .ok();

    event_loop.run(None, &mut data, move |_| {})?;

    Ok(())
}
