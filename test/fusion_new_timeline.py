import sys
import time
import DaVinciResolveScript as dvr

r = dvr.scriptapp("Resolve")
p = r.GetProjectManager().GetCurrentProject()
mp = p.GetMediaPool()
clips = [c for c in (mp.GetRootFolder().GetClipList() or []) if c.GetName() == "clip.mp4"]
name = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh"
tl = mp.CreateTimelineFromClips(name, clips)
if tl is None:
    sys.exit(f"не удалось создать таймлайн {name}")
p.SetCurrentTimeline(tl)
tl.SetCurrentTimecode("00:00:00:00")
r.OpenPage("fusion")
time.sleep(3)
c = r.Fusion().GetCurrentComp()
print("comp:", c.GetAttrs().get("COMPS_Name"))
print("tools:", [(t.GetAttrs().get("TOOLS_RegID"), t.GetAttrs().get("TOOLS_Name")) for t in (c.GetToolList() or {}).values()])
c.CurrentTime = 4.0
