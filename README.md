# Live Polling App

A live polling app: a host creates a poll with a question and multiple options,
participants join with a code and vote, and everyone watches the results update in
real time. One person hosts, everyone else votes, results update live for all of them.

Built with a FastAPI (REST) + Socket.IO (real-time) backend and a small built-in web
frontend. REST handles creating a poll, reading a poll and its results, and the host
closing a poll. Socket.IO handles joining a poll's live room, submitting an answer,
and broadcasting the updated tally to everyone in that room the moment a vote comes
in. Each poll has a short join code; a host gets a poll code to share, and
participants join with that code and a display name to start voting.

Answers are validated and authorized server-side (a participant can't vote twice or
vote on an option that isn't part of the poll, and only the host who created a poll
can close it), and results are backed by a real database so the tally is always
consistent for everyone watching, not just cached in the browser.

See `CLAUDE.md` for the full spec this was built against, `ARCHITECTURE.md` for a
one-page overview of how the pieces fit together, and `docs/CONCEPTS_APPLIED.md` for
where each concept was actually applied in the code.
