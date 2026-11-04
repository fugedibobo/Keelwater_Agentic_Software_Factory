<role>
Write one realistic {source} record for Keelwater, a UK claims-handling software company.
</role>
<record>
{record_brief}
</record>
<mentions>
{mention_briefs}
</mentions>
<noise>
{noise_brief}
</noise>
<rules>
Customers speak like claims staff. Do not use headings or bullets in speech. Use only the names in the record brief; never name a real company, product or person. Mention no feature outside the supplied glossary. Express the supplied facts in the speaker's own words. Tag each turn with its noise category or null. Do not put the planted mentions in `turns`: write each one, in the customer's own words and at least twelve words long, under `mentions[<mention id>].text`, containing that mention's `synonym` exactly as written (a mention whose form is a short agreement is different: write the internal speaker's turn stating the problem, at least twelve words and containing the synonym exactly as written, under `internal_text`, and the customer's reply of under eight words under `agreement_text`), and set after_turn to the index of the turn it should follow. The `turns` conversation is the rest of the record. Name only the people in only_people_who_may_be_named. When fin_mode is resolved or escalated, at least one turn must have speaker bot; when it is escalated, at least one turn must have speaker internal; when it is human, no turn has speaker bot. Never write any phrase listed in never_write_verbatim, including the supplied facts: paraphrase them.
</rules>
<output>
Return JSON matching the supplied source schema.
{output_schema}
</output>
