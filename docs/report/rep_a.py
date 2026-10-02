"""Sections 01 to 20: cover, front matter, introduction, problem, scope, users."""
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from rep_common import FIG, SHOT


def cover(r):
    d = r.doc
    first = None
    lines = [("", 1, False, 40), ("Daffodil International University", 14, True, 2), ("Department of Software Engineering", 12, False, 40),
             ("ShopSathi", 34, True, 6), ("An AI Sales Agent for Facebook Shops", 16, False, 30), ("Final Project Report", 22, True, 30),
             ("Course: SE-331", 13, False, 30), ("Submitted by", 11, True, 3), ("Abdullah Al Noman", 12, False, 0), ("Reduan Ahmad", 12, False, 0), ("Asraful Alam", 12, False, 24),
             ("Submitted to", 11, True, 3), ("Md. Rashedul Alam", 12, False, 0), ("Lecturer, Department of Software Engineering", 12, False, 0), ("Daffodil International University", 12, False, 24),
             ("October 2026", 12, False, 20),
             ("This report describes the system as it is implemented in the project repository.", 10, False, 0)]
    for text, size, bold, after in lines:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(after)
        if text:
            run = p.add_run(text)
            run.font.size = Pt(size)
            run.bold = bold
        if first is None:
            first = p
    r.mark(first, "01. Cover Page")


def front(r):
    r.h1("02. Declaration")
    r.p("We, Abdullah Al Noman, Reduan Ahmad and Asraful Alam, declare that this report describes the work done by our project team. The software, the tests and the documents named in it are in the project repository. "
        "Where we used other people's ideas, libraries or services, we name them in the References section.")
    r.p("We also declare that the results in this report are the results we measured. When something was only simulated, only tested on one computer, or not tested at all, the report says so. "
        "Nothing in the report claims a production deployment, a Facebook production review, real payments or a user study, because none of these was done.")
    r.p("Signature of the team representative: ____________________", space_after=4)
    r.p("Date: ____________________", space_after=16)
    r.p("Signature of the supervisor (Md. Rashedul Alam): ____________________", space_after=4)
    r.p("Date: ____________________")

    r.h1("03. Acknowledgement")
    r.p("We thank our course teacher and supervisor, Md. Rashedul Alam, Lecturer in the Department of Software Engineering at Daffodil International University, for the guidance given during the course SE-331 and for reading the proposal and the progress of the project.")
    r.p("We thank the shop owners who talk about their daily work in public groups and pages. Their problems with slow replies and lost orders gave the project its direction.")
    r.p("We also thank the open-source communities behind FastAPI, SQLAlchemy, PostgreSQL, pgvector, Redis, Celery, Next.js, LangChain and the many small libraries we used. "
        "Finally, we thank our families and friends for their patience during the long weeks of work.")

    r.h1("04. Abstract")
    r.p("Many small shops in Bangladesh sell through a Facebook or Instagram page and answer every customer by hand in Messenger. Answers are slow at night, prices and stock are asked again and again, "
        "and orders are written down in a rush. ShopSathi is a web application that helps these shops. A shop owner adds products and a policy; the AI assistant then answers customer questions in Messenger "
        "in Bangla, English or Banglish, suggests products inside a budget, collects order details, and passes difficult chats to a person.")
    r.p("The system has a Next.js dashboard, a FastAPI backend, a PostgreSQL database with pgvector, Redis and Celery for background work, and a separate AI engine package. "
        "Each shop sees only its own data. The AI uses the shop's live product data for prices and stock and checks its own replies before sending them. "
        "The AI never confirms an order; the seller reviews each draft and exports confirmed orders as a CSV file for the courier. Owners, moderators and a platform admin have different permissions.")
    r.p("The project has 63 API operations, 19 database tables and 13 migrations. The automated tests pass: 396 backend tests, 251 AI engine tests and 82 evaluation tests. "
        "A local load test with the real gpt-4o-mini model, 50 simultaneous chats and 20 shops gave a 90th percentile reply time of 5.8 seconds against the 8 second target. "
        "A real-model run on 32 sample evaluation cases gave 100% intent accuracy on 16 checks and 93.8% price and stock accuracy on 16 checks, which is below the 95% target. "
        "The team's 200-message labelled test set does not exist yet, so these figures are not final accuracy results.")
    r.p("All Messenger tests used a simulated Facebook (a fake Graph API and signed test events). The system was not connected to a real Facebook Page, was not reviewed by Facebook, and was not deployed to a public server. "
        "Payments are a simulation. This report documents what is built, how it was tested, and what is still missing.")
    r.p("**Keywords:** AI sales assistant, Messenger, multi-tenant SaaS, retrieval, pgvector, FastAPI, Next.js, Bangladesh.")


def lists(r, toc_entries, fig_entries, tab_entries):
    r.h1("05. Table of Contents")
    r.toc(toc_entries)
    r.h1("06. List of Figures")
    r.list_of("Figure", fig_entries)
    r.h1("07. List of Tables")
    r.list_of("Table", tab_entries)


def abbreviations(r):
    r.h1("08. Abbreviations")
    rows = [("AI", "Artificial intelligence"), ("API", "Application programming interface"), ("BDT", "Bangladeshi taka"), ("BR", "Business rule"),
            ("CORS", "Cross-origin resource sharing"), ("CRUD", "Create, read, update, delete"), ("CSV", "Comma-separated values"), ("DB", "Database"),
            ("ER", "Entity relationship"), ("FK", "Foreign key"), ("FR", "Functional requirement"), ("HMAC", "Hash-based message authentication code"),
            ("HNSW", "Hierarchical navigable small world (a vector index)"), ("HTTP / HTTPS", "Hypertext transfer protocol (secure)"), ("JSON", "JavaScript object notation"),
            ("JWT", "JSON web token"), ("LLM", "Large language model"), ("NFR", "Non-functional requirement"), ("OAuth", "Open authorisation standard used for Facebook login"),
            ("ORM", "Object-relational mapper (SQLAlchemy)"), ("PII", "Personally identifiable information"), ("PK", "Primary key"), ("PSID", "Page-scoped user id (Messenger customer id)"),
            ("RAG", "Retrieval-augmented generation"), ("RBAC", "Role-based access control"), ("SaaS", "Software as a service"), ("SMTP", "Simple mail transfer protocol"),
            ("SQL", "Structured query language"), ("TTL", "Time to live"), ("UC", "Use case"), ("UI / UX", "User interface / user experience"), ("UML", "Unified modelling language")]
    r.table(["Short form", "Meaning"], rows, [3.6, 12.0], "Abbreviations used in this report", size=9.5)


def introduction(r):
    r.h1("09. Introduction")
    r.h2("9.1 Overview")
    r.p("ShopSathi is an AI sales assistant for small shops that sell on Facebook and Instagram in Bangladesh. The name means \"shop friend\". "
        "The owner puts the shop's products, prices, stock and delivery rules into a web dashboard. The assistant reads this data and answers customers in Messenger. "
        "It can talk in Bangla script, in English or in Banglish (Bangla written with English letters), which is how many customers really write.")
    r.p("The assistant does not decide on its own what the shop sells or what it costs. Prices, stock and delivery charges are read from the shop's data every time. "
        "When a customer wants to buy, the assistant collects the name, phone number, address and the product choice, and creates a draft order. The seller must confirm it. "
        "When a customer is angry, asks for a refund or asks for a person, the assistant stops and the seller takes over from the Inbox.")
    r.h2("9.2 What this report contains")
    r.p("This is the final report of the project. It follows the 76 sections required for submission. It describes the system that exists in the project repository on the date of this report, and it uses the source code, "
        "the database migrations, the test results and the running application as its sources. The report does not describe planned features as if they were finished. "
        "Every part that is not implemented or not verified is marked in the text.")
    r.h2("9.3 How to read the status words")
    r.table(["Word", "Meaning in this report"],
            [("Implemented", "The code exists in the repository."), ("Tested", "An automated test or a recorded manual run checks it and passes."),
             ("Simulated", "Tested with a stand-in: the mock AI, a fake Facebook Graph API, a stub Send API, or a simulation script."),
             ("Real model", "Tested with the real OpenAI model (gpt-4o-mini) and real OpenAI embeddings."),
             ("Not tested", "Code exists but no test or run covers it."), ("Not implemented", "Not implemented in the current version.")],
            [3.4, 12.2], "Status words used in this report")
    r.h2("9.4 Report structure")
    r.p("Sections 09 to 20 explain the problem and the proposed system. Sections 21 to 31 give the requirements and the behaviour of the system with diagrams. "
        "Sections 32 to 44 describe the architecture, the database and the user interface. Sections 45 to 50 document the API, the AI engine and security. "
        "Sections 51 to 60 explain testing and results. Sections 61 to 68 cover deployment, results, limits and future work. Sections 69 to 76 hold the conclusion, references and appendices.")


def background(r):
    r.h1("10. Background")
    r.h2("10.1 Selling on Facebook in Bangladesh")
    r.p("A large number of small businesses in Bangladesh sell clothes, cosmetics, food and gifts through Facebook pages and groups. Customers write to the page in Messenger. "
        "The owner, or one helper, answers each message, writes down orders, and sends the delivery details to a courier. There is usually no shop system behind it.")
    r.h2("10.2 Language")
    r.p("Customers write in Bangla script, in English, and very often in Banglish, for example \"Red saree ta ache?\" or \"Dam koto?\". There is no fixed spelling in Banglish. "
        "A useful assistant must understand all three and reply in the same style.")
    r.h2("10.3 Technology background")
    r.bullets(["**Large language models (LLM)** can read a customer message and return structured data (intent, product, size) or write a reply. They can also invent facts, so their answers must be checked.",
               "**Embeddings** turn text into a list of numbers. Texts with a similar meaning get similar numbers, so the system can find the right product even when the customer uses different words.",
               "**pgvector** is a PostgreSQL extension that stores embeddings and searches them by distance.",
               "**Messenger Platform** lets a Facebook Page receive customer messages by webhook and reply with the Send API. A Page may reply freely only within 24 hours after the customer's last message.",
               "**Multi-tenancy** means many shops share one system, and each shop must see only its own data."])


def problem(r):
    r.h1("11. Problem Statement")
    r.p("Small shop owners lose sales and time because they answer customer messages by hand. The main problems are:")
    r.bullets(["Customers wait for hours when the owner is busy or asleep, and many leave.", "The same questions (price, stock, size, delivery charge, return rule) are answered again and again.",
               "Orders written in chat are incomplete: a phone number is missing or has a typing error, or the size is not clear.",
               "Angry customers and refund requests need a person, but the owner does not notice them in a long list of chats.",
               "There is no simple record of how many orders came from chat, and the courier needs a list of confirmed orders."])
    r.p("The project needs a system that answers common questions at any time, collects orders correctly, hands difficult chats to a person quickly, and keeps each shop's data private.")


def motivation(r):
    r.h1("12. Motivation")
    r.p("Big shopping sites have order systems, but a home-based seller with ten to a hundred products does not use them. Chat is the shop. "
        "A tool that works inside Messenger, understands Banglish, and costs little can make a real difference for such sellers.")
    r.p("The team also wanted to learn how to build a safe AI product. A chatbot that guesses prices or confirms orders by itself can harm a small shop. "
        "So the project has a strict design rule: the AI may talk, but the shop's data and the seller's decisions stay in control. "
        "This rule shaped many parts of the system: live data for prices, code checks for phone numbers, draft orders, and hand-over to a person.")


def objectives(r):
    r.h1("13. Objectives")
    r.numbered(["Let a shop owner create an account and a shop, and add products, photos and a delivery and return policy.",
                "Answer customer questions about price, stock, sizes, colours and delivery in Bangla, English and Banglish using only the shop's data.",
                "Suggest up to three in-stock products inside the customer's budget.",
                "Collect order details in chat, validate the phone number, and create a draft order that only the seller can confirm.",
                "Detect complaints, refund requests, abuse and requests for a human, stop the AI in that chat and tell the seller.",
                "Connect a Facebook Page, receive Messenger messages safely, and reply only inside the 24-hour window.",
                "Give the seller an Inbox, order pages, a CSV export for the courier, simple reports and a weekly AI summary.",
                "Keep every shop's data separate, with owner, moderator and platform admin roles.",
                "Limit AI use by plan, record the AI usage and cost per shop, and give the platform admin tools to manage shops.",
                "Measure the system with automated tests, a load test and an evaluation harness, and report the results honestly."])


def scope(r):
    r.h1("14. Scope")
    r.h2("14.1 In scope (implemented)")
    r.bullets(["Web dashboard for owners and moderators, and admin pages for the platform admin (30 page and layout files in the Next.js app).",
               "REST API with 63 operations, plus the Facebook OAuth callback.", "Product management with photos, search and CSV or Excel import.",
               "Shop policy and delivery charges.", "AI engine with language detection, understanding, retrieval, suggestions, order collection, hand-over and reply checking.",
               "Test Chat for the owner, and Messenger chats through a webhook and a Celery worker.", "Inbox with pause, resume, resolve and manual reply.",
               "Orders with draft, confirm, cancel, edit and CSV export.", "Reports and weekly AI insights.", "Plans, monthly AI reply limits and usage tracking; simulated payment.",
               "Platform admin: shops, plans, AI usage and cost, system health.", "Shop deletion and log masking.", "Docker images and a production compose file."])
    r.h2("14.2 Out of scope or not done")
    r.bullets(["Instagram messaging: Not implemented in the current version.", "Real online payments (bKash, Nagad, cards): Not implemented in the current version. Payment is a simulation.",
               "Direct courier integration: Not implemented in the current version. The seller exports a CSV file.",
               "Facebook production approval (App Review): Not done. Messenger was tested only with a simulated Facebook.",
               "Public production deployment: Not done. The Docker stack was run only on a developer computer.",
               "Voice and image understanding: Not implemented. Non-text messages are stored as a placeholder and handed to the seller.",
               "A mobile app: Not implemented. The web dashboard is responsive.", "Automatic stock reduction when an order is confirmed: Not implemented (a test confirms that stock is not changed).",
               "A user study with real shop owners: Not done."])


def target_users(r):
    r.h1("15. Target Users")
    r.table(["User", "Description", "Main needs"],
            [("Shop owner", "Runs a small Facebook shop; may not be technical.", "Add products quickly, see that the AI answers correctly, take over when needed, confirm orders, send a list to the courier."),
             ("Moderator", "A helper who answers chats and handles orders for the owner.", "Read the Inbox, reply, pause the AI, confirm or cancel orders. No access to settings, products or Facebook."),
             ("Customer", "A person who writes to the shop's Page on Messenger.", "Quick answers on price, stock and delivery, in the language they write; an easy way to order; a human when needed."),
             ("Platform admin", "A member of the ShopSathi team.", "See all shops, suspend a shop, change plans, watch AI cost and system health.")],
            [3.0, 5.2, 7.4], "Target users")


def existing(r):
    r.h1("16. Existing System")
    r.p("The usual way today is fully manual. The owner opens Messenger on a phone, reads each message, types the answer, copies the price from a note, and writes orders in a notebook or a spreadsheet. "
        "Some shops use Facebook's built-in quick replies or an away message. These help with a greeting or a fixed answer, but they cannot read the customer's question, check live stock, or collect an order.")
    r.p("Several chatbot builders exist for Messenger. They are mostly based on fixed menus and keywords, they need set-up work for every question, and they do not understand Banglish well. "
        "We did not test any of these products in this project, so this report makes no comparison with them.")


def existing_problems(r):
    r.h1("17. Existing Problems")
    r.table(["Problem in the manual way", "Effect on the shop"],
            [("Slow replies at night and during busy hours", "Customers leave before they get an answer"), ("Same questions answered many times", "Owner's time is wasted"),
             ("Prices and stock come from memory or old notes", "Wrong prices are quoted; sold-out items are offered"),
             ("Orders typed by hand in chat", "Missing or wrong phone numbers and addresses; delivery fails"),
             ("Complaints are lost in a long chat list", "Unhappy customers wait longest"), ("No summary of what customers ask", "The owner does not know which products are missing from the shop"),
             ("Order list for the courier is built by hand", "Slow and full of copy mistakes")],
            [7.4, 8.2], "Problems of the manual way of selling")


def proposed(r):
    r.h1("18. Proposed System")
    r.p("ShopSathi puts an assistant between the customer and the seller. The seller keeps control; the assistant does the repeated work.")
    r.table(["Problem", "How ShopSathi handles it"],
            [("Slow replies", "The worker answers a Messenger message in about 6 seconds (measured locally with the real model)."),
             ("Repeated questions", "The AI answers from the product table, the policy and the delivery areas."),
             ("Wrong prices or stock", "Prices and stock are read live from the database. The reply is checked: numbers must come from the facts."),
             ("Bad orders", "Code validates the phone number, product, size, colour and stock. The seller confirms."),
             ("Lost complaints", "7 hand-over reasons flag the chat, pause the AI and create a notification."),
             ("No overview", "Reports and a weekly AI summary of customer questions and missing products."),
             ("Courier list", "Confirmed orders export as a CSV file.")],
            [4.2, 11.4], "How the proposed system answers the problems")
    r.p("The system has three parts: the dashboard where the seller works, the backend with its background worker, and the AI engine. "
        "A Facebook Page is connected by the owner through Facebook login. The architecture is shown in section 32.")


def stakeholders(r):
    r.h1("19. Stakeholders")
    r.table(["Stakeholder", "Interest", "Influence on the system"],
            [("Shop owner", "More sales with less time spent", "Defines products, policy and what the AI may say; confirms orders"),
             ("Moderator", "Easy daily work", "Replies and handles orders within the owner's shop"),
             ("Customer", "Fast and correct answers", "Their messages drive the AI; their data must be protected"),
             ("Platform admin / project team", "A working, safe and affordable service", "Plans, limits, suspension, cost control"),
             ("Courier companies", "Complete addresses and phone numbers, fewer failed deliveries", "Indirect: receive the CSV list from the seller outside the system"),
             ("Course supervisor", "A well-built, honestly reported project", "Reviews proposal, progress and this report"),
             ("Meta (Facebook)", "Apps that follow the platform rules", "Controls the Messenger API, the 24-hour window and App Review"),
             ("AI provider (OpenAI, Google)", "Fair API use", "Supplies the language models and embeddings; cost and speed depend on them")],
            [4.0, 5.2, 6.4], "Stakeholders")


def roles(r):
    r.h1("20. User Roles")
    r.p("The `users` table has a `role` column with three values. A database CHECK makes sure that a platform admin has no shop and that owners and moderators have one. "
        "The role is read from the database on every request, not trusted from the token.")
    r.table(["Area", "Owner", "Moderator", "Platform admin"],
            [("Sign up, log in, reset password", "Yes", "Log in, reset", "Log in"), ("Products, import, photos", "Yes", "No", "No"), ("Shop policy and delivery", "Yes", "No", "No"),
             ("Staff (add moderators)", "Yes", "No", "No"), ("Plan view", "Yes", "Yes", "No"), ("Plan change", "Yes", "No", "No (admin changes a plan through /admin)"),
             ("Facebook Page connection", "Yes", "No", "No"), ("Test Chat", "Yes", "No", "No"), ("Inbox and replies", "Yes", "Yes", "No"), ("Orders and CSV export", "Yes", "Yes", "No"),
             ("Notifications", "Yes", "Yes", "No"), ("Reports and weekly summary", "Yes", "No", "No"), ("Delete shop", "Yes", "No", "No"),
             ("All shops, suspend, plans, AI usage, health", "No", "No", "Yes")],
            [6.0, 2.8, 2.8, 4.0], "Permissions by role")
    r.p("The table is generated from the access rules that the test `test_role_matrix.py` checks for every endpoint with four kinds of caller: anonymous, owner, moderator and platform admin.")
