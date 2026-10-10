Build a workflow named research-learn.
- The gate must verify the teach-back report is a nonempty string.
- The gate must verify each claim quotes a string found in a local page file under --pages, or the line is marked unverified.
- The gate must verify an uncited claim fails with the error citations-missing.
- The gate must verify the explainer HTML file exists and contains the topic string.
- The gate must verify the quiz has at least 1 question and a matching answer key.
- The gate must verify the flashcards file is a nonempty string.
- The router must judge only the --request string. A --pages path must not be a forbidden target.
- Fixture mode must pass with the bundled local pages and must not fetch a URL.
