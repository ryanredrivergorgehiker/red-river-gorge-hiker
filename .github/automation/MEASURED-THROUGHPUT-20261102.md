# Expanded-source throughput increment

The first expanded production wave103 (41530574852) independently recovered
9 jobs / 93 full-quality tiles: three Hiking, three Terrain and three leaf-off.
It used 118.305 producer wall seconds, 283,967,488 public-source bytes and 205
public-source requests. It had no pixel gaps; hashes, pixels, native package
chunks and cache preservation passed on the separate recovery runner.

The next controlled increment selects at most four fresh jobs from each of
those three families. It must not deploy until wave104 independently succeeds.
This increases the maximum batch output from 93 to 124 interior tiles; actual
output depends on border geometry and independent source-pixel acceptance.

Each child still reserves its full 600-second allowance on failure. Twelve
worst-case failed children consume 7,200 seconds, leaving 1,800 seconds inside
the unchanged 9,000-second producer slot. Source byte/request sums are checked
against that actual slot during planning and trusted publication. Every other
resource limit, job quality check, ownership fence, source pin, receipt and
accepted/excluded history remains unchanged. There is no new concurrency,
256-job assumption, automatic retry or accepted-data rewrite.

The earlier source rollback remains available. A tested future control digest
can also restore the 3/3/3 allocation prospectively without resetting state or
replaying consumed work. This increment is not a complete product ETA.
