# Wikimedia refresh requests

Catalogue discovery, article batches and background details share a serial HTTP
gate, with at least 0.5 seconds between responses and the next request. The existing
contact User-Agent and `maxlag=5` remain mandatory. Three preparation workers do
not create three simultaneous requests.

HTTP 429/502/503/504, connection failures and maxlag payloads use at most three
attempts. Retry-After supports delta seconds and HTTP dates; missing/malformed
values use exponential backoff. A single delay above 30 seconds or one exceeding
the 60-second request budget fails rather than retrying too early. The shared
cooldown also applies to subsequent workers. Permanent HTTP/API errors fail
without retries. Every response is closed.

An exhausted refresh remains a failure. Catalogue and article files are written
only after complete collection, so the previous successful snapshot/date is
preserved. A synthetic retry test is not evidence of a fresh live catalogue.
Scheduled CI still requires a real successful refresh and the existing catalogue,
backend and browser checks before deployment.

References: [Action API etiquette](https://www.mediawiki.org/wiki/API:Etiquette),
[Wikimedia rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits),
and [maxlag](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter).
