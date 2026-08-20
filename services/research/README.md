# Research service

The research service owns ingestion, point-in-time normalization, feature
generation, scoring, and reproducible research runs. It is deliberately
separate from the web application so that research runs can be versioned and
validated independently of presentation.

No provider integrations or model logic are present yet. P1.2 introduces the
first shared data contracts; P1.3 introduces persistent storage.
