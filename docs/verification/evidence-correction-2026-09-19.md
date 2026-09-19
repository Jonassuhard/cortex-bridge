# Release evidence correction — 19 September 2026

Release acceptance is not established. Earlier completion and publication-ready
claims are retracted. No code, validator threshold or provider permission is
changed by this correction.

- The three mini-site runs were validator fixtures with preset browser results,
  not measured browser sessions or executor missions.
- The API write-file scenario uses scripted assistant responses. It is an
  integration test, not a live ChatGPT/model round trip.
- The 0.6.5 manifest copied timing measurements and acceptance counts from
  0.6.1 without fresh source evidence. Those current-release claims are removed.
- The referenced crash report identifies its own older source commit. Assigning
  a newer sourceCommit in the manifest did not rerun the tests.
- The declared environment and generation time were not captured by the
  manifest-writing command. They are not retained as verified metadata.
- The privacy check failed on two new documents. The correction removes the
  personal reference and private interpreter path from their current contents.
- An unexecuted live test is NOT_RUN, not evidence of a provider-terms violation.

The manifest retains historical suite counts explicitly as historical reports.
Unverified current measurements are null. The existing release validator must
reject this incomplete manifest; it has not been weakened to accept it.

Revalidation requires actual live context transfer and receipt, an executor
mission, freshly captured performance/crash evidence and lifecycle evidence.
Existing commits are preserved, including the original reports. Their private
content therefore remains in local Git history and must be reviewed before
publication; a clean current-file privacy scan alone does not clear that history.

## Checks executed for this correction

- CI-configured privacy scan: PASS, 454 text files and 92 images.
- Offline link check: PASS, 142 links; 49 external URLs skipped by this check.
- Release-validator unit tests: 24 PASS.
- Release manifest validation: FAIL as expected; incomplete evidence is rejected.
- `git diff --check`: PASS. The validator and its thresholds are unchanged.

These checks validate the documentation correction, not the application release.
