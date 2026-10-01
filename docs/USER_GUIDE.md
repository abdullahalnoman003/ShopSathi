# ShopSathi user guide

ShopSathi is an AI sales assistant for small online shops. When a customer writes to your **Facebook Page** on Messenger,
the AI answers questions about your products, prices, stock, delivery and shop rules in **Bangla, English or Banglish**,
suggests products, and collects the details of an order. **You** check and confirm every order.

Part 1 is for **shop owners and moderators**, Part 2 for the **platform administrator**. Page names in **bold** are menu
items in the dashboard. The dashboard works on a phone (use the **Menu** button at the top) and on a laptop.

## What the AI does and does not do

| The AI does | The AI never does |
|---|---|
| Answers with the **price, size, colour and stock exactly as in your product list** | **Confirm an order.** It only makes an *order draft*; you confirm it |
| Answers delivery charges and rules from your **shop policy** | **Change a price, give a discount** or promise one |
| Suggests up to three products that are in stock, with price and photo | **Take payment.** Payment, packing and delivery stay with you (cash on delivery, bKash and so on are arranged by you) |
| Asks for the missing order details (product, size, colour, quantity, name, phone, address) and asks again if the phone number is not a valid Bangladeshi number | **Invent** a product, price, size or delivery area. If your data does not have the answer it says it will check with the shop and **hands the chat to you** |
| Tells the customer it is an automatic assistant (at the first reply) | Reply to a customer more than **24 hours** after their last message (Facebook's rule) |
| Hands the chat to you when the customer complains, asks for a refund, is rude, asks for a person, asks something unrelated, or when the AI is not sure | Keep answering a chat after it handed it to you, until you turn the AI back on |

Facebook only lets a Page answer **within 24 hours after the customer's last message**. After that you can reply only
when the customer writes again.

---

# Part 1. Shop owners and moderators

## 1. Sign up and choose a plan (about 1 minute)

1. Open the ShopSathi address and click **Sign up**.
2. Enter your **shop name**, **your name**, **e-mail** and a **password** (at least 8 characters).
3. Choose a plan:
   * **Free**: 100 AI replies a month, to try ShopSathi.
   * **Basic**: 1,000 AI replies a month. **Pro**: 5,000 AI replies a month.
   * Prices and limits shown on the page are the current ones and may change. Paying is **simulated** in this version: for Basic or Pro you click **Continue** and then **Confirm simulated payment and create account**; no money, card or mobile-banking number is used.
4. Click **Sign up** (Free) or **Continue** (Basic and Pro). You are now logged in as the **owner**.

You can change the plan later in **My plan**. The page shows how many AI replies you used this month. When the monthly
limit is reached the AI stops replying until next month or until you choose a bigger plan; customers' messages are still kept so you can answer them yourself.
Forgot your password? Click **Forgot password?** on the login page: you get an e-mail with a link.

## 2. Add your products (the AI only knows what you enter)

**Products** > **Add product**. Fill in:

* **Name**, **price** (in ৳), **stock count**, and optionally a description.
* **Sizes** and **colours**: type one and press Enter or comma (for example `M`, `L`, `XL`). Leave empty if the product has none.
* **Photos**: up to 5 per product (JPEG, PNG or WebP). The first photo is shown to customers with suggestions.

Click **Add product** to save it. A product with **stock 0** is never suggested and the AI says it is out of stock. Edit or delete a product from the list. **Keep stock and prices up to date: the AI repeats what you wrote.**

**Many products at once:** **Products** > **Import from CSV/Excel**. Download the template, fill it in Excel or as a CSV file, and upload it.
Columns: `name, description, price, sizes, colours, stock, photos`. Separate several sizes or colours with `|` (for example `M|L|XL`).
Photos are web addresses (http/https). The page lists every row that could not be imported and why, and imports the good rows.

## 3. Write your shop policy

**Shop policy**: enter your **delivery time**, **return rules**, **payment options**, and the **delivery areas with their charge** (for
example `Inside Dhaka` 60, `Khagan` 100). The AI quotes the charge only for areas you list; for any other area it
checks with you.

## 4. Try the AI in the Test chat (about 1 minute)

**Test chat** (owner only). Click **Start new test conversation** and write like a customer, for example
`Cotton Panjabi er dam koto?`, `XL ache?`, or `Khagan e delivery charge koto?`. Nothing is sent to Facebook and nothing counts
against your monthly limit. If the answer is wrong, fix the product or policy data and ask again. Try an order too:
`Cotton Panjabi nibo, XL, 2 ta`; the AI will ask for your name, phone and address, then show an **order draft** card.
A test conversation that the AI hands over shows a red "flagged" note; start a new test conversation to continue.

## 5. Connect your Facebook Page

Owner only. **Facebook Page** > **Connect Facebook Page**.

1. Log in with Facebook and allow the permissions (they let ShopSathi read and answer messages of your Page).
2. You come back to ShopSathi: choose your Page from the list and click **Connect this Page**. You must be an admin of that Page.
3. Done: the page shows **Connected** and the Page name. From now on customers' messages reach the AI.

To stop, click **Disconnect** (the AI then no longer sees messages of that Page). One Facebook Page per shop. If the page says
a setting is missing, the person who runs ShopSathi still has to enter the Facebook app details.
While ShopSathi's Facebook app is in testing mode only people added as testers on the app can use it.

## 6. The inbox: read chats and take over (owner and moderator)

**Inbox** lists the Messenger chats. **Flagged** chats (the AI handed them to you) are at the top with a red badge and the reason
(for example "Customer complaint", "Refund request", "Customer asked for a person", "Not in your shop data"). Use the **Flagged** / **All** buttons to filter.
Click a chat to read the whole conversation: customer messages, the AI's replies (with the products and order drafts it showed) and your own.
On a phone the list and the conversation are separate screens (use **Back to inbox**).

* **Pause AI**: the AI stops answering this chat and you can reply yourself. You can pause **any** chat at any time. A chat the AI flagged is already paused.
* **Reply** box: enabled only while the AI is paused **and** the 24-hour window is open. If the window has closed, a notice tells you; you can answer when the customer writes again. Your replies are sent from your Page and are **not** counted as AI replies.
* **Mark flag as handled**: removes the "flagged" mark and marks its notifications as read. It does **not** turn the AI back on.
* **Resume AI**: gives the chat back to the AI.

**Notifications:** the bell at the top shows how many flagged chats are new. Click one to open that chat; **Mark all as read** clears the list.

## 7. Orders: confirm, edit, cancel (owner and moderator)

When a customer has given all details, the AI creates an **order draft** (and tells the customer the shop will confirm it). In **Orders**:

* The tabs **Draft**, **Confirmed** and **Cancelled** show the orders; open one to see all details and a link to the chat it came from.
* **Edit** (drafts only): change product, size, colour, quantity, name, phone or address. The phone must be a valid Bangladeshi mobile number; size and colour must be options of the product. The price cannot be typed in: it comes from your product list (choosing another product takes that product's price).
* **Confirm order**: after the dialog, the order becomes *Confirmed*. **ShopSathi stops here**: you arrange payment, packing and delivery yourself. Confirmed orders cannot be edited or cancelled in ShopSathi.
* **Cancel order**: after the dialog, the order becomes *Cancelled*.

**Export for the courier:** at the bottom of **Orders** choose a date range (by the day you confirmed the orders; leave empty for all) and click **Export confirmed orders (CSV)**. The file opens in Excel, with Bangla text shown correctly, and has the columns
`order_id, confirmed_at, customer_name, customer_phone, customer_address, product_name, size, colour, quantity, unit_price, total_price`.

## 8. Reports and the weekly AI summary (owner)

**Reports** shows, for the dates you choose (default: last 7 days), four numbers: **messages handled by AI**, **chats handed to humans**, **orders drafted** and **orders confirmed**. Test chats are not counted.

Below, the **Weekly AI summary** (made automatically every Monday for the week before) lists the **top 5 customer questions** and the **products customers asked for that you don't have**: useful for deciding what to stock. Pick another week with the week selector. The counts are approximate. Names, phone numbers and addresses are removed before the AI reads the messages.

## 9. Staff accounts: Moderators (owner)

**Staff** > add a moderator with a name, e-mail and password; share these with the person. A **moderator** can use the **Inbox** (read chats, pause/resume the AI, reply, handle flags) and **Orders** (edit, confirm, cancel, export). A moderator cannot see products, policy, Facebook connection, plan, reports, staff or settings.

## 10. Delete your shop (owner)

**Settings** > **Danger zone: delete shop**. This **permanently** removes the shop and everything in it: products and photos, policy, **all chats and messages with your customers (including their names, phone numbers and addresses)**, all orders, reports and summaries, the Facebook connection, and the accounts of you and your moderators. It **cannot be undone**. Type your password and the exact shop name, then confirm. You are logged out and taken to the sign-up page.

## 11. Quick answers

* *The AI did not answer a customer.* The chat may be paused or flagged (see the Inbox), the monthly limit may be reached (**My plan**), the Page may be disconnected (**Facebook Page**), or the customer's last message is older than 24 hours.
* *The AI gave a wrong price.* Check the product in **Products**; the AI repeats your data. If the product data is right, tell the person who runs ShopSathi.
* *A customer sent a photo or voice message.* The AI cannot read these: the chat is handed to you.

---

# Part 2. Platform administrator

The platform administrator is created by the person who runs the system (not through sign-up). Log in on the normal login page: you are taken to the admin area. The admin sees **shops, plans, AI costs and system health**, never a shop's chats, customers or orders, and cannot act as a shop user.

## Shops

**Shops** lists every shop with its owner e-mail, plan, status, connected Facebook Page and this month's AI replies against its limit. Search by shop name or owner e-mail. Open a shop for its product, chat and order **counts**.

* **Suspend**: after a confirmation, the shop's users can no longer log in or use the dashboard (even if already logged in) and the AI stops answering its customers. Use it for shops that break the rules (spam, fake or misleading offers).
* **Reactivate**: restores access and the AI.
* **Change plan**: choose Free, Basic or Pro and confirm. No payment is recorded for an admin change.

Every suspend, reactivate and plan change is recorded with your name and the time.

## Plans

**Plans** edits each plan's **monthly AI reply limit** and the **price shown** to shops (display only). Changes apply at once to all shops on that plan.

## AI usage & cost

**AI usage & cost**: choose a date range (default: last 30 days) to see, per shop, the number of AI calls, tokens and the **estimated cost in US dollars** (also split by kind of work: replies, understanding, embeddings, weekly summaries), and the total. The estimate uses the configured model prices; the real bill is in the AI provider's account.

## System health

**System health** shows whether the API, the database, Redis and the background worker work, and how many jobs wait in the queue. A queue that keeps growing means the worker is stopped or too small: tell the person who runs the servers. **Check again** refreshes it.
