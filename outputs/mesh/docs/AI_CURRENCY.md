# Owner insight currency

GET /api/v1/ai/owner accepts an optional currency query parameter containing exactly three uppercase letters, for example ?currency=USD. Finance data is always filtered by organization and currency; no exchange conversion or cross-currency addition is performed.

If omitted, the only recorded currency is selected automatically. With no cost records the historical INR default remains, with zero observed months. Multiple recorded currencies return409 and require an explicit selection. This corrects the prior hardcoded INR summary that silently missed USD demo costs. Explicitly selecting an empty currency intentionally produces zero observations; it does not establish zero spending in every currency.

The response has an additive nullable currency field. Owner numeric context retains recorded_spending_inr for INR and uses recorded_spending_<lowercase-currency> for other currencies. Provider inputs remain bounded numeric aggregates; email, payroll, raw events and credentials are not added. Existing authorization/revocation and accounting controls remain unchanged.

POST /api/v1/ai/stream accepts the same optional currency field only for purpose=owner. Other purposes reject currency. Streaming uses the same resolution and separation rules. Existing callers omitting the field remain supported.

The configured local-deterministic provider is still a template and is labelled accordingly. This fix does not enable a paid/external language model, create a new AI policy or complete the friend-owned R5 enhancement workstream. The frontend has not gained a new currency selector in this backend checkpoint; when multiple currencies exist clients must submit the selected currency.
