// ATANOR Orb Overlay — pins the ATANOR window as a resident, always-on-top,
// all-workspaces overlay so the particle sphere floats over the real desktop.
// It does NOT capture input globally (no keylogging); it only manages the ATANOR
// window's stacking + placement. Everything else on the desktop behaves normally.
import Meta from 'gi://Meta';
import GLib from 'gi://GLib';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

export default class AtanorOrbExtension extends Extension {
    enable() {
        this._ids = [];
        // pin any current + future ATANOR window
        global.get_window_actors().forEach((a) => this._maybePin(a.meta_window));
        this._createId = global.display.connect('window-created', (_d, win) => {
            // give the window a moment to get its title, then pin if it is ours
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => { this._maybePin(win); return GLib.SOURCE_REMOVE; });
        });
        this._ids.push([global.display, this._createId]);
    }

    _isAtanor(win) {
        if (!win) return false;
        const t = (win.get_title() || '').toLowerCase();
        const cls = (win.get_wm_class() || '').toLowerCase();
        // the living wallpaper ('ATANOR WALLPAPER', retyped to DESKTOP by
        // orb-wallpaper.sh) must stay on the background layer — never pin it
        if (t.includes('wallpaper')) return false;
        if (win.get_window_type() === Meta.WindowType.DESKTOP) return false;
        return t.includes('atanor') || cls.includes('atanor');
    }

    _maybePin(win) {
        if (!this._isAtanor(win)) return;
        try {
            win.make_above();                 // always on top
            win.stick();                      // visible on every workspace
            if (win.is_skip_taskbar && !win.is_skip_taskbar()) {
                // keep it out of the alt-tab clutter where supported
            }
        } catch (_e) { /* window may have closed */ }
    }

    disable() {
        for (const [obj, id] of (this._ids || [])) {
            try { obj.disconnect(id); } catch (_e) {}
        }
        this._ids = [];
        // unpin so the desktop returns to normal on disable
        global.get_window_actors().forEach((a) => {
            const w = a.meta_window;
            if (this._isAtanor(w)) { try { w.unmake_above(); w.unstick(); } catch (_e) {} }
        });
    }
}
