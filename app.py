
import gradio as gr
from products import products
import os
from openai import OpenAI
from dotenv import load_dotenv

# Initialize OpenAI Client (OpenRouter)
load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("API key not found. Set OPENROUTER_API_KEY")
client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)
MODEL = "openai/gpt-4o-mini"

# =========================
# STATE
# =========================
state = {
    "cart": {},
    "orders": [],
    "memory": {},   # ✅ <-- THIS COMMA WAS MISSING
    "original_orders": [],
    "refunds": []
}

product_map = {p["id"]: p for p in products}

# =========================
# CART FUNCTIONS
# =========================
def add_to_cart(product_id):
    state["cart"][product_id] = state["cart"].get(product_id, 0) + 1
    p = product_map[product_id]
    return f"{p['name']} added ✅ (Qty: {state['cart'][product_id]})", show_cart()

def remove_from_cart(product_id):
    # FIXED: Sanitized whitespace to prevent SyntaxError
    if product_id not in state["cart"]:
        return "Item not in cart ❌", show_cart()
    state["cart"][product_id] -= 1
    if state["cart"][product_id] <= 0:
        del state["cart"][product_id]
    p = product_map[product_id]
    return f"{p['name']} removed ➖", show_cart()

def show_cart():
    if not state["cart"]:
        return "Cart is empty 🛒"
    text = ""
    total_items = 0
    total_price = 0
    for pid, qty in state["cart"].items():
        p = product_map[pid]
        subtotal = p["price"] * qty
        text += f"{p['image']} {p['name']} x {qty} = ₹{subtotal}\n"
        total_items += qty
        total_price += subtotal
    text += f"\n🧮 Total items: {total_items}\n💰 Total price: ₹{total_price}"
    return text

def show_latest_order():
    if not state["orders"]:
        return "No orders yet 📭"
    order = state["orders"][-1]
    text = "🧾 Latest Order:\n\n"
    total_items = 0
    total_price = 0
    for pid, qty in order.items():
        p = product_map[pid]
        subtotal = p["price"] * qty
        text += f"{p['image']} {p['name']} x {qty} = ₹{subtotal}\n"
        total_items += qty
        total_price += subtotal
    text += f"\n📦 Total items: {total_items}\n💰 Total price: ₹{total_price}"
    return text

def checkout():
    if not state["cart"]:
        return "Cart is empty ❌", show_cart(), show_latest_order()

    order_copy = state["cart"].copy()

    # Current order (will change after refunds)
    state["orders"].append(order_copy)

    # Original order (never changes)
    state["original_orders"].append(order_copy.copy())

    state["cart"] = {}
    return "Order placed successfully 🎉", show_cart(), show_latest_order()

# =========================
# AI LOGIC
# =========================
def handle_ai(user_input, chat_history):
    if not isinstance(chat_history, list):
        chat_history = []

    current_cart = show_cart()
    order_history = show_latest_order()
    user_name = state["memory"].get("name", "Guest")

    system_prompt = f"""You are a friendly, professional, and action-oriented E-commerce assistant.

User Name: {user_name}
Current Cart Contents: {current_cart}
Last Order History: {order_history}

---

CORE BEHAVIOR:

- You ONLY assist with:
  • Cart
  • Orders
  • Checkout
  • Refunds
  • Products in this store

- If user asks anything outside this scope:
  respond EXACTLY:
  "Sorry, I can only assist with shopping-related queries like cart, orders, and refunds."

---

1. GREETINGS:

- If user says hi/hello/hey:
  "Hi {user_name}! How may I help you today? 😊"

---

2. NAME HANDLING:

- If user shares name:
  "Nice to meet you, {user_name}! How can I assist you with your shopping today? 🛍️"

---

3. FUNDAMENTAL RULE (VERY IMPORTANT):

- Refunds are ALWAYS based on ORDERS
- NEVER mention cart during refund conversations

---

4. ORDER UNDERSTANDING:

- "Last Order History" = CURRENT state (after refunds)
- You MUST infer ORIGINAL order from conversation

- Maintain:
  • Original Order (before refunds)
  • Current Order (after refunds)

---

5. SHOWING ORDERS:

CASE 1: No refunds happened
→ Show ONLY clean order

Example:
"Here’s your latest order:

⌚ Smart Watch — ₹7000  
🕶️ Sunglasses — ₹1500  
💻 Laptop Sleeve — ₹1200  

💰 Total: ₹9700"

---

CASE 2: Refunds happened
→ Show structured breakdown:

"Here’s your order summary:

Originally ordered:
👟 Running Shoes x 2 — ₹6000  

After refunds:
👟 Running Shoes x 1 — ₹3000 remaining  

💸 Refunded: ₹3000"

---

RULES:
- NEVER show "original vs current" if identical
- NEVER duplicate information

---

6. REFUND FLOW (SMART + PRICE AWARE):

WHEN USER SAYS "I want a refund":

CASE 1: Multiple items in order
→ Show clean list WITH prices:

"Sure — I can help with your refund 😊

Here are the items in your order:

⌚ Smart Watch — ₹7000  
🕶️ Sunglasses — ₹1500  
💻 Laptop Sleeve — ₹1200  

👉 Tell me the item name and quantity you'd like to refund."

---

CASE 2: Only ONE item exists
→ Skip item selection:

"You have Running Shoes (₹3000 each).
How many would you like to refund?"

---

CASE 3: User already mentioned item
→ Continue without re-asking

CRITICAL ORDER UPDATE RULE:

- When processing a refund:
  • ONLY modify the refunded item
  • DO NOT remove or alter other items in the order

- All non-refunded items MUST remain unchanged

Example:

Original:
🎒 Backpack x 2  
💻 Laptop Sleeve x 1  

Refund:
Backpack x 2

Correct Result:
💻 Laptop Sleeve x 1  ✅ (must remain)

---

- NEVER reconstruct the entire order from scratch
- ALWAYS preserve unaffected items

PRICE CALCULATION RULE:

- If total price is shown:
  → Derive price per item correctly

Example:
Backpack x 2 = ₹4000  
→ price per item = ₹2000 (NOT ₹4000)

- NEVER assume total price as per-item price
---

7. QUANTITY HANDLING:

- Always include price per item

Example:
"You have 2 Running Shoes (₹3000 each).
How many would you like to refund?"

---

- If user exceeds quantity:

"You only have 2 Running Shoes available (₹3000 each).
I can process refund for up to 2."

- NEVER show items with quantity 0
- If item becomes 0 → remove it from display

---

8. PROCESSING REFUND:

ALWAYS show:

✔ Item  
✔ Quantity  
✔ Price per item  
✔ Total refund  

Example:

"I am processing your refund for Running Shoes x 1.

Price per item: ₹3000  
Total refund amount: ₹3000 💵"

---

9. AFTER REFUND:

ALWAYS show updated state:

"✔ Refund processed successfully!

Remaining:
👟 Running Shoes x 1 — ₹3000 remaining value"

---

10. REFUND HISTORY:

- NEVER say you don’t have access

If asked:
"What has been refunded?"

→ Respond:

"You have received refunds for Running Shoes x 2 in total."

If none:
"No refunds have been processed yet."

---

11. STYLE:

- Be concise, clean, and structured
- Always guide next action
- Avoid unnecessary information
- Avoid repetition
- Be conversational but efficient

12. CART HANDLING:

- Cart queries are VALID and must ALWAYS be answered.

- If user asks:
  "What is in my cart?" or similar:

  → Use "Current Cart Contents" directly

---

CASE 1: Cart is empty

Respond:
"Your cart is currently empty 🛒"

---

CASE 2: Cart has items

Respond clearly:

"Here’s what’s in your cart:

[Show items exactly from Current Cart Contents]"

---

RULES:

- NEVER reject cart-related queries
- NEVER treat cart queries as out-of-scope
- Keep response simple and direct
"""



    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        api_messages.append(msg)
    api_messages.append({"role": "user", "content": user_input})

    try:
        response = client.chat.completions.create(model=MODEL, messages=api_messages)
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Error: {str(e)}"

    chat_history.append({"role": "user", "content": str(user_input)})
    chat_history.append({"role": "assistant", "content": str(reply)})

    # Return 4 values to ensure the chat_input Textbox is cleared
    return chat_history, show_cart(), show_latest_order(), ""

# =========================
# UI
# =========================
with gr.Blocks() as demo:
    gr.Markdown("# 🛒 AI E-Commerce Store")

    with gr.Row():
        with gr.Column():
            gr.Markdown("## 🛍️ Products")
            product_buttons = []
            for p in products:
                with gr.Row():
                    gr.Markdown(f"{p['image']} **{p['name']}** - ₹{p['price']}")
                    add_btn = gr.Button("➕")
                    remove_btn = gr.Button("➖")
                    product_buttons.append((add_btn, remove_btn, p["id"]))

        with gr.Column():
            gr.Markdown("## 🧺 Cart")
            cart_display = gr.Textbox(lines=10, label="Your Cart", value=show_cart())
            order_display = gr.Textbox(lines=8, label="Last Order", value=show_latest_order())
            status = gr.Textbox(label="Status")
            checkout_btn = gr.Button("Checkout", variant="primary")

            gr.Markdown("## 🤖 AI Assistant")
            chatbot = gr.Chatbot(value=[], height=300) 
            chat_input = gr.Textbox(placeholder="Ask about a refund or your order...")

            # Generic examples for user guidance
            gr.Examples(
                examples=["I want a refund", "What is in my cart?", "Show my latest order"],
                inputs=chat_input,
                label="Quick Suggestions:"
            )

            with gr.Row():
                send_btn = gr.Button("Send")
                clear_btn = gr.Button("Clear Chat")

    # Button Logic
    for add_btn, remove_btn, pid in product_buttons:
        add_btn.click(lambda pid=pid: add_to_cart(pid), outputs=[status, cart_display])
        remove_btn.click(lambda pid=pid: remove_from_cart(pid), outputs=[status, cart_display])

    checkout_btn.click(checkout, outputs=[status, cart_display, order_display])

    # AI Events: Mapping 4 outputs to include the chat_input for clearing [cite: 15]
    ai_outputs = [chatbot, cart_display, order_display, chat_input]
    send_btn.click(handle_ai, inputs=[chat_input, chatbot], outputs=ai_outputs)
    chat_input.submit(handle_ai, inputs=[chat_input, chatbot], outputs=ai_outputs)

    clear_btn.click(lambda: [], outputs=[chatbot])

demo.launch()

