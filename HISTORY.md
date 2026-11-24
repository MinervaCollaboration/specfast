# KiwiSpec / MINERVA instrument history

Hardware events that can affect the RVs, from site-visit summaries and logs.
Each entry gives the date, what changed and what it means for specfast
(eras, per-telescope breaks, exclusions). Dates are the summary's date when
the exact day of a change is not known. Newest first. Telescopes are T1-T4; "MINERVA Red"
is the separate fifth telescope, which does not feed KiwiSpec.

## 2024-11 site trip (summary 2024-11-20)

- **Mirrors:** M1 and M3 cleaned on all five telescopes.
- **Collimation:** four of five collimated (T1, T2, T4 and MINERVA Red).
  T3 could not be collimated: two of its secondary trusses were failing and
  were replaced (they had been coming unglued since 2018). The failure left
  T3 misaligned: its beam is vignetted and best focus is highly aberrated,
  and it may need special tooling.
- **T3 also:** M3 fixed (potentiometer on the M3 board); filter-wheel
  drivers reinstalled.
- **Rotators:** USB-to-serial converters replaced on several.
- **Rotator angles and pointing models** redone for three of five
  telescopes. T1 is collimated but its drives seem to lose encoder counts,
  so it has no usable pointing model.
- **Status after the trip:** T1 and T3 offline pending PlaneWave.
- Also (no KiwiSpec effect): MINERVA Red revived and an IR camera installed
  on it; the Aqawan 2 rail fixed before it derailed; an AO team's system
  aligned.

What it means for specfast (from the star frames in the telbreaks master
table):
- **Before the trip:** after the warm CCD (instrument era e2024 from
  2024-03-15) the only lit telescope was T3 (2024-10-22 .. 11-16).
- **After the trip:** no star frames 2024-11-17 .. 2025-11-21. From
  2025-11-22 T1 and T2 are lit; T3 is dark and T4 nearly so (one frame in
  2026-01).
- So T1 and T2 have no data between 2022-11 and 2025-11, and their
  2025-11 LSF-width and gradient change cannot be split between the
  2024-03-15 instrument era and this trip's cleaning and collimation. Both
  fall in the same gap, so no extra break is needed for them.
- **T3 after 2024-11-20:** if it returns, it needs its own break; until it
  is realigned, its data are suspect (vignetted, aberrated: low
  throughput and a different LSF).

## 2019-09 site trip (unsent draft summary, 2019-09-20)

At the end of the 2019 monsoon gap (no science 2019-07-25..09-18); the
instrument era e2019 starts 2019-09-18.

- **Spectrograph room HVAC:** for about two weeks before the trip it had not
  been cooling the spectrograph room, and the spectrograph warmed by ~3 C.
  A faulty contactor was replaced. The unit has little heating capacity (it
  was designed for data centres); a duct heater was to be quoted. Earlier
  space heaters had broken quickly.
- **Temperature sensors:** they had dropped out, and the watchdog ignored
  the failed readings, so the excursion went unnoticed. The watchdog now
  warns when a critical sensor is silent for more than 10 minutes.
- **Rotation calibration bug:** the rotator calibration script had saved the
  same image under two names and computed the rotation angle from the
  pair. This gave an erroneous rotator offset and probably lengthened
  acquisition; how widespread it was is unknown. Fixed, at the cost of
  0.3 s more overhead per guide exposure.
- Windows 10 control computers in preparation (mini PCs in the telescope
  bases; they arrived with the 2021-09 "back online").
- MINERVA Red's FAU working with the MINERVA software (no KiwiSpec effect).

What it means for specfast:
- This is the e2019 break (2019-09-18). The instrument-log analysis found
  thermal regulation lost across the 2019 monsoon gap: bench 25.11 C in
  2019-02, then 25.6-26.2 C and drifting until 2020-02. The
  contactor fix did not restore the earlier regulation, so within e2019,
  regress on bench temperature (as for e2021).
- The sensor dropout explains the PT100 logging gap (2019-02-26..09-18) and
  the missing TEMP* headers (2019-03..07): spectrograph temperature is
  unknown for most of 2019 H1. The HVAC failure itself fell in the monsoon
  gap, so no science frames were taken warm.
- Rotator offsets were wrong before this trip, for an unknown period. They
  set where the star lands relative to the fibre at acquisition, so they
  are a candidate cause of slow acquisition and the guide-start stalls
  before 2019-09. They are not a direct RV term.

## 2018-12 site trip (summaries 2018-12-18 and 2018-12-21)

No science 2018-12-15..19; robotic operation resumed 2018-12-21 (the first
science frames are on 12-20).

- **T3:** repaired after a cable-wrap failure: the telescope had wrapped up
  about 7 times. Every cable in the telescope conduit (and a few others)
  was replaced. A PlaneWave software upgrade was still pending.
- **Guide cameras:** ZWOs replaced the SBIGs on the FAUs. They could not
  communicate through the black boxes (no fix from ZWO), so the telescope
  computers were moved back into the domes (they had been moved out after
  three motherboards died) and talk through the mount's USB hub.
- **FAUs refocused and pointing models redone** for the ZWOs. The larger
  field of view and better QE made a big difference to guiding, but they
  cause source confusion for some targets (55 Cnc), which confuses
  acquisition.
- MINERVA Red (not a KiwiSpec feed): dome gearboxes replaced; east shutter
  sticking.

What it means for specfast:
- This is the per-telescope break 2018-12-17 (T2 and T3) in
  `kiwispec.yaml`. T2's starlight throughput rose by 1.3 dex (~20x
  relative to the other telescopes) and its FAU star size fell 2.1": the
  new guide cameras and refocus fixed T2's acquisition and guiding, which
  the 2018-09 refocus had not. T3's step is the recabling, after a mostly
  dark 2018 H2.
- The header fibre positions change units on 2018-12-20 (ZWO pixels):
  any guide-offset or fibre-position quantity needs a per-camera scale.
- 55 Cnc after 2018-12: check for acquisition failures (wrong star or
  off-fibre frames) before trusting its RVs.

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

## 2017-02 site trip (summaries 2017-02-21 .. 2017-03-01)

Closed from about 2017-02-20; full RV operation resumed 2017-03-01 (no
science frames 2017-01-19..03-01).

- **Science fibres re-terminated (all four):** the fibre ends were cut off,
  re-epoxied and re-polished. A test fibre gave a little over 2x the
  throughput of the original. Six fibres were made. The best four were
  matched, fibre and end, to the telescope each suited best, so
  fibre-to-telescope assignments may have changed. The test fibre was in
  the bottom two and became the calibration fibre. Throughput was "well
  over" 2x and roughly uniform across telescopes. End-to-end variability was
  a factor of ~2, more than the ~30% expected from a 5 um decenter.
- **Fibres refocused in their FAUs.** New data fibres for the black boxes
  were run through the same conduits.
- **Telescope computers moved into the control room.** USB devices now
  go through each telescope's black box. Telescope control panels now
  talk through the network switch, not USB.
- Aqawan roof limit switches moved and the Aqawan 2 U-joint replaced
  (enclosure only).
- A focusing-routine bug was found and fixed on 03-01; pointing models
  might need redoing.

What it means for specfast:
- **A candidate break for all four telescopes at 2017-02-27:** new fibre
  ends (near- and far-field, throughput, possibly a different fibre per
  telescope) change the trace profile, the LSF and the per-telescope
  zero-point. The x2 extraction already starts a profile era on 2017-02-25
  (e2017a). The data show steps across the 01-19..03-01 gap: header fibre
  positions on all four telescopes on 03-01, and relative throughput and
  trace-profile shape on T1, T3 and T4 on 03-04..15. `kiwispec.yaml` has
  no RV-level break here: the instrument era e2016c runs 2016-11-22 ..
  2017-10-01, with the vacuum outage excluded from 04-25. The telbreaks
  RV test tried only T4 at 2017-03-08 (no gain). An all-telescope break at
  2017-02-27 is untested.
- Throughput per telescope roughly doubles here, so faint-frame selection
  and S/N-based weights should not assume one throughput across the break.
