import sys, time
import DaVinciResolveScript as dvr

r = dvr.scriptapp("Resolve")
pm = r.GetProjectManager()
prev = pm.GetCurrentProject()
print("prev project:", prev.GetName() if prev else None)
if prev:
    print("save:", pm.SaveProject())

name = "CK Compose Test"
ok = pm.CreateProject(name)
print("create:", ok)
p = pm.GetCurrentProject()
print("current:", p.GetName() if p else None)

mp = p.GetMediaPool()
clips = mp.ImportMedia(["/mnt/king4tb/CODE/corrridor/demo/clip.mp4"])
print("imported:", [c.GetName() for c in (clips or [])])
if not clips:
    sys.exit("import failed")

tl = mp.CreateTimelineFromClips("ck_test", clips)
print("timeline:", tl.GetName() if tl else None)
if tl:
    p.SetCurrentTimeline(tl)
    tl.SetCurrentTimecode("00:00:00:00")
print("items:", [i.GetName() for i in (tl.GetItemListInTrack("video", 1) or [])] if tl else None)

r.OpenPage("fusion")
time.sleep(3)
f = r.Fusion()
c = f.GetCurrentComp()
print("comp:", c)
if c:
    print("comp name:", c.GetAttrs().get("COMPS_Name"))
    print("tools:", list(c.GetToolList().values()))
print("page:", r.GetCurrentPage())
