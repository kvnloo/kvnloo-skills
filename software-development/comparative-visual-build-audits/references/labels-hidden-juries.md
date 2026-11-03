# Labels-hidden A/B juries

Use when judges must compare panels without knowing which side is the baseline, the candidate or the reference. Call this labels-hidden, not double blind: the operator who builds the pack knows the mapping.

## Build and freeze the pack

1. Put only anonymous panels, clips and a neutral brief in an allowlisted directory with origin-free file names.
2. Randomize A and B per panel. Store the mapping, source paths and hashes in a separate map file that judges cannot read.
3. Compose panels with aspect-preserving letterboxing. Do not crop a multi-row sheet to fill a square cell. Check canvas size, expected view count, first and last rows and labels before dispatch.
4. Hash every panel and freeze. A layout fix after freeze makes a new version and a new ballot round. Never overwrite a frozen pack or reuse ballots cast against a broken version.
5. Give every judge the same allowlist and forbid reading source, history, parent directories, neighboring runs or the map.

## Judge

- Refer to entries only as A and B. Describing the medium ("3D render") is fine; naming source, project, baseline or expected winner is not.
- Score on an absolute 0 to 10 scale. If the same artifact recurs in another panel, keep its score unless the crop or duration changes what can be judged.
- A forced choice is not approval. Name the winner and say when both miss the bar. If the brief forces a choice, do not escape with a tie; use low confidence instead.
- For stills, mark timing, camera stability and foot-plant continuity as not assessable.
- Panel letters are local. Never sum A or B votes across panels as if the letters meant the same source.

## Inspect motion without playback

1. Probe duration, size, frame rate and stream count.
2. Sample the full clip at a declared rate (6 fps is a reasonable first pass for a short clip) and add denser windows around impacts, turns and cuts.
3. Burn timestamps after cropping each side, so both side sheets stay labeled.
4. Build side-isolated sheets for anatomy, feet and contact, and a combined sheet for synchronized staging.
5. Check the sample count equals duration times rate and that first and last timestamps are present.
6. Re-confirm left is A and right is B against a labeled still before scoring.
7. Keep extracted frames in a temp directory and delete them after the verdict.

Example with ffmpeg:

```bash
ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate -of json clip.mp4
ffmpeg -i clip.mp4 -vf "fps=6,crop=iw/2:ih:0:0,drawtext=text='%{pts\:hms}':x=8:y=8:fontcolor=white:box=1,tile=6x6" -frames:v 1 "$TMPDIR/A-sheet.png"
ffmpeg -i clip.mp4 -vf "fps=6,crop=iw/2:ih:iw/2:0,drawtext=text='%{pts\:hms}':x=8:y=8:fontcolor=white:box=1,tile=6x6" -frames:v 1 "$TMPDIR/B-sheet.png"
```

## Accept a ballot

- Check the judge's tool trace shows it actually loaded each image. A process exit or a self-reported evidence list is not enough.
- Validate ballot field names against the brief and assert the expected panel count, so a wrong file glob cannot produce an empty "pass".
- Unblind panel by panel only after all ballots are final. Compute tallies with a tool and keep anonymous ballots next to the map so the tally can be audited.
- Say whether judges were separated by process only or by an OS sandbox.

## Ballot shape

```json
{
  "panel_1": {
    "winner": "A|B|TIE",
    "scores": {"A": 0, "B": 0},
    "blocking_defects": ["A: defect with timestamp", "B: defect with timestamp"],
    "rationale": "craft-only paragraph using A and B only"
  },
  "overall": "cross-panel synthesis without naming sources or expected winners"
}
```
