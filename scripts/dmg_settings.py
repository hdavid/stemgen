"""dmgbuild settings — classic drag-to-install layout.

Invoked by `make dmg`:
    dmgbuild -s scripts/dmg_settings.py -D app="dist/StemGen.app" \
        "StemGen" "dist/StemGen.dmg"

Layout: the .app on the left, a /Applications symlink on the right, over
assets/dmg/background.tiff (arrow + caption). Icon-center coordinates here
must stay in sync with the geometry in scripts/make_dmg_background.py.
"""

import os.path

app = defines.get("app", "dist/StemGen.app")  # noqa: F821 — dmgbuild injects `defines`
appname = os.path.basename(app)

# Volume ---------------------------------------------------------------------
format = "UDZO"
filesystem = "HFS+"
icon = "assets/icons/StemGen.icns"

# Contents -------------------------------------------------------------------
files = [app]
symlinks = {"Applications": "/Applications"}
icon_locations = {
    appname: (166, 170),
    "Applications": (494, 170),
}

# Window ---------------------------------------------------------------------
background = "assets/dmg/background.tiff"
window_rect = ((200, 140), (660, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

# Icon view ------------------------------------------------------------------
icon_size = 128
text_size = 13
arrange_by = None
show_icon_preview = False
show_item_info = False
label_pos = "bottom"
