# Primary documentation and implementation references

Reviewed 4 November 2026. Use the current documents for API versions and account-specific setup. This source package is a pilot, not a guarantee of Meta account eligibility or ChatGPT workspace permissions.

- OpenAI, building an MCP server with `search` / `fetch` compatibility and ChatGPT connection: https://developers.openai.com/api/docs/mcp
- OpenAI, OAuth metadata, PKCE, audiences, scopes and token verification: https://developers.openai.com/plugins/build/auth
- Official MCP Python SDK source: https://github.com/modelcontextprotocol/python-sdk
- Official MCP Python SDK v1 docs: https://py.sdk.modelcontextprotocol.io/v1/
- Official MCP Python SDK resource-server authorization: https://py.sdk.modelcontextprotocol.io/v1/authorization/
- MCP authorization specification: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- Meta, official WhatsApp Business Platform API collection: https://www.postman.com/meta/whatsapp-business-platform/overview
- Meta, webhook subscription collection: https://www.postman.com/meta/whatsapp-business-platform/folder/6lt7to2/webhooks
- Meta, media download request: https://www.postman.com/meta/whatsapp-business-platform/request/zsq66eh/download-media
- WhatsApp Business Messaging Policy: https://whatsappbusiness.com/policy/
- WhatsApp, exporting chats: https://faq.whatsapp.com/1180414079177245/

For constraints, these are current first-party integration documents from official providers about their WhatsApp integrations:

- 360dialog, Coexistence history window, media window, sync timing and echoes: https://360dialog.com/blog/whatsapp-coexistence-sync/
- 360dialog, Groups API eligibility/limits: https://docs.360dialog.com/docs/messaging/groups
- 360dialog, Coexistence onboarding: https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence
- Bird, existing groups not synchronised through Coexistence: https://bird.com/docs/guides/whatsapp/coexistence/troubleshooting

Meta's developer-guide URLs below returned rate-limit errors during this session. They are included as authoritative destinations to verify in the account setup, not represented as successfully fetched pages:

- https://developers.facebook.com/documentation/business-messaging/whatsapp/groups
- https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
- https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/history/
