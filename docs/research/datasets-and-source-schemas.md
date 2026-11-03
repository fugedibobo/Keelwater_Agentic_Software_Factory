# Research: public datasets and source-system record shapes

Researched 02/11/2026. FOUND = checked at the source URL; INFERRED = reasoned.

**Research summary for the Keelwater demo (02/11/2026): public datasets, record shapes, recommendation**

**Q1. Public datasets.** Fit is scored 1–5 for "B2B, insurers, claims software".
Sales calls:
- DeepMostInnovations/saas-sales-conversations (https://huggingface.co/datasets/DeepMostInnovations/saas-sales-conversations). FOUND: Apache-2.0, 100,000 rows, a single 7.17 GB CSV with 3,088 columns including embeddings, GPT-4 synthetic, B2B SaaS focus. Redistributable and B2B, but generic SaaS and too big to vendor. Fit 3.
- gong-io-research/call-playbook (https://huggingface.co/datasets/gong-io-research/call-playbook). FOUND: "Gong License", gated, about 3 MB, speaker-tagged snippets from 50 real B2B calls with entities replaced; not full transcripts. Fit 3. INFERRED: not redistributable (gated, custom licence, terms unseen).
- liva-ai/mock-sales (https://huggingface.co/datasets/liva-ai/mock-sales). FOUND: licence "other", gated, scripted software-sales role-plays, about 900 h of audio. Fit 2. INFERRED: not redistributable.

Support:
- Bitext (https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset). FOUND: cdla-sharing-1.0, 26,872 Q/A pairs, CSV; intents are account/order/refund/invoice/payment. INFERRED: consumer-retail flavour, so not B2B. Redistributable under CDLA-Sharing terms (INFERRED: share-alike on the data). Fit 2.
- Tobi-Bueck/customer-support-tickets (https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets). FOUND: cc-by-nc-4.0, about 61.8k tickets in English and German, fields subject, body, answer, type, queue, priority, tag_1 to tag_8; IT-heavy helpdesk. Fit 3. Non-commercial, so cite only.
- irongateprd/support-ticket-intents (https://huggingface.co/datasets/irongateprd/support-ticket-intents). FOUND: CC-BY-4.0, 1,500 templated tickets with fields ticket_id, subject, body, intent, sentiment, priority, channel. Redistributable, not B2B. Fit 2.
- ABCD (https://github.com/asappresearch/abcd). FOUND: MIT per the README nav, over 10K human-human dialogues, 55 intents, retail scenario. Redistributable, B2C. Fit 2.
- KazKozDev/synth-customer-support-expanded-R (https://huggingface.co/datasets/KazKozDev/synth-customer-support-expanded-R). FOUND: MIT, 438 e-commerce rows. Fit 1.
- MultiWOZ (https://github.com/taoyds/multiwoz). FOUND: about 10k travel/city-services dialogues; the page shows both Apache-2.0 and MIT. Fit 1.

Other routes:
- Onboarding and account-manager notes: no public set found. The closest is AMI (https://groups.inf.ed.ac.uk/ami/corpus/), where FOUND: CC BY 4.0 covers signals and transcripts, 100 h of design-team meetings. Fit 1.
- Product feedback: sealuzh/app_reviews (https://huggingface.co/datasets/sealuzh/app_reviews). FOUND: licence "unknown", 288,065 reviews of about 395 F-Droid apps, fields package_name, review, date, star. Consumer, not safe to redistribute. Fit 1.
- Clickstream: Kaggle REES46 (https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store). FOUND: 285M events, licence not stated on the page; the Nov-2019 file alone is 9 GB. E-commerce with no rage or dead-click flags. Fit 1. I found no public B2B session-replay data.
- Demo-data websites: I found no single well-known site for sales-call, support-ticket and onboarding data. Hugging Face and Kaggle are the hosts above. Consensus (ex-Saleo) injects prospect-specific data into live product demos; it is not a dataset site (https://goconsensus.com/saleo-login). Search hits I did not open: Twilio synthetic call generator (https://github.com/wittyreference/twilio-synthetic-call-data-generator) and Salesforce Org Data Generator (https://www.salesforce.com/blog/org-data-generator/). INFERRED: Mockaroo-style tools make tabular rows, not transcripts (not checked).

**Q2. Record shapes (key fields only)**
- **Gong, transcript.** Doc: https://help.gong.io/apidocs/retrieve-transcripts-of-calls-by-date-or-callids-v2callstranscript-2.md. FOUND: `POST /v2/calls/transcript` with body `{filter:{fromDateTime,toDateTime,workspaceId,callIds[]},cursor}`.
  - Response: `{requestId, records:{totalRecords,currentPageSize,currentPageNumber,cursor}, callTranscripts:[{callId, transcript:[{speakerId, topic, sentences:[{start,end,text}]}]}]}`.
  - `start` and `end` are integer ms from call start. There is no speaker name here; join `speakerId` to `parties[].speakerId`.
- **Gong, call and CRM context.** Doc: https://help.gong.io/apidocs/retrieve-detailed-call-data-by-various-filters-v2callsextensive-2.md. FOUND: `POST /v2/calls/extensive` returns `calls[]` with:
  - `metaData{id,url,title,scheduled,started,duration,primaryUserId,direction,system,scope,media,language,workspaceId,purpose,meetingUrl,isPrivate,calendarEventId}`.
  - `context[{system, objects[{objectType,objectId,fields[{name,value}],timing:Now|TimeOfCall}]}]`. The doc example uses Salesforce; INFERRED: `system:"HubSpot"` works the same.
  - `parties[{id,emailAddress,name,title,userId,speakerId,affiliation:Internal|External|Unknown,methods[],context[]}]`.
  - `content{topics[{name,duration}],trackers[{id,name,count,type,occurrences[{startTime,speakerId}]}],brief,keyPoints[{text}],outline[],callOutcome{id,category,name}}` and `interaction{speakers[{id,userId,talkTime}],interactionStats[],questions{companyCount,nonCompanyCount}}`.
  - The plain calls list (`GET /v2/calls`) has `id,title,scheduled,started,duration,primaryUserId,direction,scope,media,language,workspaceId,url`. I only saw that shape in a third-party TypeScript client (https://glama.ai/mcp/servers/@JustinBeckwith/gongio-mcp/blob/c802d9a31aa39b66a9933c0f3c4bccf051d00616/src/gong.ts).
- **Intercom.** Docs: https://developers.intercom.com/docs/references/rest-api/api.intercom.io/conversations/retrieveconversation, https://developers.intercom.com/docs/references/2.6/rest-api/conversations/conversation-model and https://developers.intercom.com/docs/references/rest-api/api.intercom.io/conversations/listconversations. FOUND:
  - List: `GET /conversations?per_page&starting_after` returns `{type:"conversation.list",conversations[],total_count,pages{page,per_page,total_pages,next{starting_after}}}`.
  - Conversation: `type,id,created_at,updated_at,source{type,id,delivered_as,author,attachments},contacts{contacts[]},teammates,admin_assignee_id,team_assignee_id,state(open|closed|snoozed),priority,tags{type:"tag.list",tags[]},custom_attributes{},conversation_rating,statistics,ai_agent,ai_agent_participated,conversation_parts{type:"conversation_part.list",conversation_parts[],total_count}`. Parts are capped at the latest 500.
  - Part: `type,id,part_type,body,created_at,updated_at,notified_at,assigned_to,author{type:user|admin|bot,id,name},attachments,redacted`.
  - Rating: `{created_at, contact{id,type}, rating 1-5, remark, teammate{id,type:"admin"}}`.
  - Fin shows as `ai_agent` plus `ai_agent_participated`. The ai_agent fields are `source_type`, `source_title`, `last_answer_type`, `resolution_state`, `rating` (1-5), `rating_remark` and `content_sources` (https://app.unpkg.com/intercom-client@6.4.0/files/dist/api/resources/aiAgent/types/AiAgent.d.ts). `source_type` is one of essentials_plan_setup, profile, workflow, workflow_preview, fin_preview.
  - INFERRED: Fin's own replies appear as parts with `author.type:"bot"`; the docs don't spell this out. The allowed `resolution_state` strings are not documented.
- **Fireflies.** Doc: https://docs.fireflies.ai/graphql-api/query/transcript. FOUND: `transcript(id)` returns `id,title,date,dateString,duration,host_email,organizer_email,participants[],speakers{id,name},meeting_attendees{displayName,email,name},transcript_url`.
  - `sentences{index,speaker_id,speaker_name,text,raw_text,start_time,end_time,ai_filters{task,pricing,metric,question,sentiment}}`.
  - `summary{overview,short_overview,gist,short_summary,bullet_gist,action_items,keywords,outline,topics_discussed,meeting_type}`.
  - The doc's sample shows `action_items` as a string, not an array. Times are floats in seconds.
- **FullStory.** Docs: https://developer.fullstory.com/anywhere/warehouse/events/ and https://developer.fullstory.com/destinations/bigquery/. FOUND: warehouse event row `{event_id,event_time,processed_time,updated_time,device_id,session_id,view_id,event_type,event_properties(JSON),source_type,source_properties}`. The BigQuery page lists `event_id`, `processed_time` and `updated_time`; the events-model page doesn't.
  - Event types include click, page_view, navigate, load, request, exception, console_message, custom, element_seen, form_abandon, mouse_thrash, copy and paste.
  - Rage, dead and error clicks are not separate types. They are `click` events with `fs_rage_count>0`, `fs_dead_count=1` or `fs_error_kind` (unknown|console|exception).
  - `page_view` carries `page_name,start_time,end_time,duration_millis,max_scroll_depth`; `custom` carries `event_name,event_properties`; `exception` carries `message,exception_source_file,is_exception_handled`.
  - Connections made after 31 July 2025 use "Ready to Analyze Views", which I could not read (robots-blocked).
  - Session list is `GET` list-sessions, which "returns up to `limit` most recent session replay URLs" by `uid`, `email` or `session_uid` (https://developer.fullstory.com/server/sessions/list-sessions/). The response schema was not readable. INFERRED: a row of `{userId, sessionId, createdTime, fsUrl}`.
- **HubSpot company.** Docs: https://developers.hubspot.com/docs/api-reference/latest/crm/objects/companies/guide and https://developers.hubspot.com/docs/api-reference/crm-companies-v3/basic/get-crm-v3-objects-companies.
  - FOUND: `GET /crm/v3/objects/companies/{id}?properties=a,b`; undefined properties are omitted and empty ones come back `null`. Default properties include `name,domain,industry,lifecyclestage,hs_object_id`.
  - FOUND: custom properties are created via `/crm/v3/properties/companies` and read like defaults.
  - FOUND: `annualrevenue` as a company property (only seen in https://docs-platform.crewai.com/platform/en/integrations/hubspot; HubSpot's own KB lists an "Annual revenue" label without the internal name).
  - INFERRED: envelope `{id, properties:{...}, createdAt, updatedAt, archived}`, with property values as strings. Tier and renewal date would be custom properties, for example `keelwater_tier` and `renewal_date`.
- **Shortcut story.** The official page (https://developers.shortcut.com/api/rest/v3) is robots-blocked, so I used a mirror (https://www.withone.ai/knowledge/shortcut/conn_mod_def%3A%3AGJ7HD39Ab5U%3A%3AYNpQlYX2R9-PolY6b5xhIw/md). FOUND: `id,name,description,story_type(feature|bug|chore),app_url,workflow_state_id,workflow_id,epic_id,project_id,group_id,labels[{id,name,color}],label_ids,owner_ids,requested_by_id,estimate,deadline,custom_fields[{field_id,value_id,value}],external_links[],story_links[{verb,subject_id,object_id}],stats,created_at,updated_at,completed,started,blocked`.
- **Notion page.** Doc: https://developers.notion.com/reference/page. FOUND: `{object:"page",id(uuid),created_time,last_edited_time,parent{type:"data_source_id",data_source_id},properties{<Name>:{id,type,...}},url,in_trash,archived}`. A title property is `{id:"title",type:"title",title:[{type:"text",text:{content},plain_text}]}`; other types are `date{start,end,time_zone}` and `status{id,name,color}`.

**Q3. Recommendation**
- Generate all data synthetically and cite the public sets as inspiration only. INFERRED reasons: none is B2B or insurer-specific; there is nothing public for onboarding, account-manager or session-replay data; the one genuine B2B transcript set (Gong) is gated under a custom licence; Tobi-Bueck is non-commercial; and the REES46 and app-reviews licences are unclear or unknown.
- The only clean, usable seeds are DeepMost (Apache-2.0, 7 GB, would need streaming) and irongateprd (CC-BY, templated). Neither is worth the attribution and size cost for a one-day build.
- Real strength of a demo here is the record shape, which Q2 gives you. Copy the field names exactly, including Gong's ms timestamps versus Fireflies' second floats, and the Fin `ai_agent` block.
- Suggested volumes, INFERRED to run in minutes with parallel LLM batches:
  - 15 HubSpot companies, with ARR, tier and renewal dates spread so some renew within 90 days.
  - 25 Gong calls, of which 8 are full 30–60-monologue transcripts and the rest short.
  - 60 Intercom conversations, about half Fin-handled, 10 escalated, with ratings and tags.
  - 20 Fireflies calls (10 onboarding, 10 account-manager).
  - 40 FullStory sessions, roughly 1,000 events.
  - 12 Shortcut stories and 10 Notion pages.
  - That is about 110 LLM-written text documents, roughly 100–150k output tokens in total.
- Generate FullStory events in code, not with the LLM, with rage and dead clicks tied to the planted themes.
- Plant 5–6 themes that recur across at least 3 routes and skew toward high-ARR accounts, plus 2 noise themes and 1 contradictory signal, so the pipeline's aggregation is visibly meaningful.
- Publish the generator and a fixed seed alongside the output so the public repo is reproducible and licence-clean.

Not checked: Kaggle licence for REES46 (page showed none), Twilio and Salesforce generators (not opened), exact `ai_agent.resolution_state` values, the FullStory list-sessions response shape, and the Shortcut official page (mirror used).
