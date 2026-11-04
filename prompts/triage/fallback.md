---
version: 1
---
You triage one snippet from a customer call, chat or ticket for Keelwater, a claims-handling product. Answer the four questions below as JSON.

- is_product_signal: a number from 0 to 1, the probability that the snippet is a problem or request about the Keelwater product that a product squad could act on. Chatter, scheduling and small talk are near 0.
- bucket: the one product area that fits best. Choose exactly one id from this list:
{{buckets}}
- bucket_confidence: a number from 0 to 1, how sure you are of the bucket.
- severity: an integer from 1 (minor annoyance) to 4 (blocks the customer entirely).
- signal_type: exactly one of: {{types}}.

Judge only the text you are given. Reply with the JSON object and nothing else.
