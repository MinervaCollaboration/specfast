# KiwiSpec / MINERVA instrument history

Hardware events that can affect the RVs, from site-visit summaries and logs.
Each entry gives the date, what changed and what it means for specfast
(eras, per-telescope breaks, exclusions). Dates are the summary's date when
the exact day of a change is not known. Telescopes are T1-T4; "MINERVA Red"
is the separate fifth telescope, which does not feed KiwiSpec.

## 2018-09 site trip (summary 2018-09-07)

During the 2018 monsoon gap (no science 2018-06-29..10-10). Spectroscopy
was not resumed until the FAU pointing models and port rotation angles
were redone.

- **Iodine cell:** reinstalled after its fresh FTS scan (the NIST 2018-08
  scan specfast uses). The cell was out of the spectrograph for the scan.
- **Collimation:** M2 and M3 recollimated on T1-T4 (M3 removed; ~4 h and two
  people per telescope). T3 was so badly out that it lost a factor of ~10
  or more at the fibre: the trusses holding its secondary were coming
  unglued and M2 had moved ~3/8". It was rigid after the fix but to be
  monitored. Animal prints on T3's mirror and secondary baffle are the
  suspected root cause. The other three were also off, less so. A hoped-for
  side effect: better alignment of the optical and rotator axes, and so
  better pointing.
- **Mirrors:** M1 and M3 cleaned on T1-T4 (diluted Simple Green, then
  distilled water); nearly as good as new. A drip on several primaries
  was oil from the M3 bearing; cleaned, but it will recur.
- **FAUs:** collimator lenses and fibre focus refocused on all four. T2 and
  T4 were particularly bad (their SBIG guide cameras had been replaced
  by site staff without an on-sky calibration).
- **Hard stops:** checked on all five telescopes; T3's (and MINERVA Red's)
  slightly loose and re-tightened. Earlier hard-stop failures on T1 and T3
  were catastrophic (2017-18 downtime). To be checked on every trip.
- **Rotators:** two of the ten died and were replaced by spares.
- **Vacuum:** lines rearranged, tip seals cleaned, preparation for a third
  (hot-spare) pump.
- **Control room:** the AC condensate pump failed; AC off pending repair.

What it means for specfast:
- **Instrument-wide:** the iodine cell was removed and reinstalled. Same
  cell, so the same atlas, but check the iodine depth and the wavelength
  zero-point across 2018-06-29..10-10.
- **Per telescope:** expect throughput, LSF and h3 changes on all four
  telescopes across the monsoon gap, largest on T3 (collimation) and on
  T2/T4 (FAU focus). In the data (FINDINGS 2026-11-23, per-telescope
  breaks), T2's LSF width fell 2.5-2.9% across the gap. Neither a T2 era
  nor a T3 era at 2018-07-01 improved the RVs; T3 was mostly dark in 2018
  H2 regardless.
- T2 stayed ~10x faint in starlight until the 2018-12 trip, so this
  refocus did not fix T2's feed problem.
