# projects/

SwitchLoc project databases (`<name>.sqlite`) live here.  The folder is
EMPTY in a fresh checkout: a project is created by **Data Import →
Import GIS data…** (one file per imported GIS folder), then opened again
with **File → Open project…**, the recent-projects list, drag-and-drop of
the `.sqlite` onto the window, or `RUN.bat projects\<name>.sqlite`.

A project written by a newer SwitchLoc build is refused instead of being
modified; upgrading an older project makes a `*.pre-migration-vN.sqlite`
backup first.
