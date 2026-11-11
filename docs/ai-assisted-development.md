# Development with OpenAI Codex

This project was built collaboratively with OpenAI Codex. AI assistance is disclosed as part of the engineering process, not presented as independent authorship of every line.

## Responsibilities

The project owner defined the use case, chose hardware, wired and assembled the device, printed and evaluated enclosure iterations, supplied acceptance feedback, and decided what to keep. Codex assisted with implementation, debugging, tests, design iterations and documentation. Repository preparation is also AI-assisted and requires owner review.

## Decisions and observed lessons

1. **Host-side rendering:** a strict 9472-byte framebuffer keeps typography off the microcontroller. Tradeoff: the host must remain available for updates.
2. **Display refresh verification:** an idle BUSY signal and a software completion message did not prove that the panel refreshed. The driver was changed to require the refresh BUSY transition; received/drawn hashes distinguish stages. The owner then visually confirmed the new layout.
3. **Enclosure tolerance:** real prints exposed carrier-hole misalignment despite an acceptable USB opening. Separate glued feet preserved the accepted socket position without guessing another fixed spacing. The repair remains documented in this release.
4. **Forecast boundaries:** deterministic Python owns the numbers; optional OpenAI commentary explains supplied facts. Neither synthetic tests nor polished text establish predictive accuracy.
5. **Failure behaviour:** retain verified data and cached frames rather than substituting convincing demo values.

## Evidence policy

Label synthetic fixtures, renders, hardware observations, local test results and remote CI results distinctly. Do not fabricate historical commits, development duration, model accuracy, power measurements or cross-platform support. Keep credentials and private conversations out of the public repository.

The next reviewer should be able to inspect decisions, reproduce checks and challenge limitations. The owner reviews this candidate before publication.
