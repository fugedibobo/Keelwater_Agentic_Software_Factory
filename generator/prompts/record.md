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
Customers speak like claims staff. Do not use headings or bullets in speech. Use only the names in the record brief; never name a real company, product or person. Mention no feature outside the supplied glossary. Express the supplied facts in the speaker's own words. Tag each turn with its mention id, noise category or null. Every tagged customer turn must contain that mention's `synonym` exactly as written, and set synonym_used to it. Never write any phrase listed in never_write_verbatim, including the supplied facts: paraphrase them.
</rules>
<output>
Return JSON matching the supplied source schema.
{output_schema}
</output>
