import random
import string
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# --- DATABASE CONNECTION ---
SUPABASE_URL = "https://pbygqrhorevuehbgdcnu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBieWdxcmhvcmV2dWVoYmdkY251Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE3NzA1MzcsImV4cCI6MjA5NzM0NjUzN30.aSkkj5xj9bqtZ2IcK2VSKMLzKZijb6qfVWmO_m89Yac"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_room_code():
    return ''.join(random.choices(string.digits, k=5))

# --- ROUTING: PAGES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# --- ROUTING: AUTH & ROOMS ---
@app.route('/create-room', methods=['POST'])
def create_room():
    password = request.json.get('password')
    if not password: return jsonify({"error": "Password required"}), 400
    room_code = generate_room_code()
    try:
        supabase.table('rooms').insert({"room_code": room_code, "password": password}).execute()
        return jsonify({"message": "Room created!", "room_code": room_code}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/join-room', methods=['POST'])
def join_room():
    data = request.json
    try:
        response = supabase.table('rooms').select('*').eq('room_code', data.get('room_code')).eq('password', data.get('password')).execute()
        if len(response.data) == 0: return jsonify({"error": "Invalid credentials"}), 401
        return jsonify({"message": "Login successful!", "room_id": response.data[0]['id']}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add-roommate', methods=['POST'])
def add_roommate():
    data = request.json
    try:
        supabase.table('roommates').insert({
            "room_id": data.get('room_id'),
            "name": data.get('name'),
            "spending_limit": data.get('limit') if data.get('limit') else None,
            "is_guest": data.get('is_guest', False)
        }).execute()
        return jsonify({"message": f"{data.get('name')} added!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ROUTING: EXPENSES ---
@app.route('/add-expense', methods=['POST'])
def add_expense():
    data = request.json
    try:
        supabase.table('expenses').insert({
            "room_id": data.get('room_id'),
            "paid_by_id": data.get('paid_by_id'),
            "amount": float(data.get('amount')),
            "category": data.get('category')
        }).execute()
        return jsonify({"message": "Expense logged!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete-expense/<expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    try:
        supabase.table('expenses').delete().eq('id', expense_id).execute()
        return jsonify({"message": "Deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reset-room/<room_id>', methods=['DELETE'])
def reset_room(room_id):
    try:
        supabase.table('expenses').delete().eq('room_id', room_id).execute()
        return jsonify({"message": "Room reset successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ROUTING: THE MASTER ALGORITHM ---
@app.route('/get-room-data/<room_id>', methods=['GET'])
def get_room_data(room_id):
    try:
        roommates_data = supabase.table('roommates').select('*').eq('room_id', room_id).execute().data
        expenses_data = supabase.table('expenses').select('*').eq('room_id', room_id).order('timestamp', desc=True).execute().data

        # 1. Setup Tracking Variables
        people = {r['id']: {'name': r['name'], 'limit': r['spending_limit'], 'paid': 0, 'should_pay': 0} for r in roommates_data}
        total_spent = 0
        mehul_paid, sujal_paid = 0, 0

        # 2. Process Every Expense & Apply Custom Roommate Rules
        for exp in expenses_data:
            amt = float(exp['amount'])
            payer = exp['paid_by_id']
            if payer in people: people[payer]['paid'] += amt
            total_spent += amt

            # Identify "Core" users (no limits, e.g., Mehul, Sujal)
            core_users = [pid for pid, p in people.items() if p['limit'] is None]

            if payer in core_users:
                # RULE 1: Mehul or Sujal paid. Split ONLY among Mehul and Sujal.
                if len(core_users) > 0:
                    split_amt = amt / len(core_users)
                    for cid in core_users:
                        people[cid]['should_pay'] += split_amt
            else:
                # RULE 2: Kyson paid. Split among EVERYONE in the room.
                if len(people) > 0:
                    split_amt = amt / len(people)
                    for pid in people:
                        people[pid]['should_pay'] += split_amt

        # 3. Determine Who Buys Next (Only checks Mehul and Sujal)
        for pid, pdata in people.items():
            name_lower = pdata['name'].lower()
            if "mehul" in name_lower: mehul_paid = pdata['paid']
            if "sujal" in name_lower: sujal_paid = pdata['paid']
            
            # Calculate final Settle Up balance
            pdata['balance'] = pdata['paid'] - pdata['should_pay']

        who_buys_next = "Mehul" if mehul_paid <= sujal_paid else "Sujal"

        # Format expenses for the frontend UI
        feed = []
        for e in expenses_data:
            payer_name = people[e['paid_by_id']]['name'] if e['paid_by_id'] in people else "Unknown"
            feed.append({"id": e['id'], "amount": e['amount'], "category": e['category'], "payer": payer_name})

        return jsonify({
            "total_spent": total_spent,
            "who_buys_next": who_buys_next,
            "roommates": list(people.values()),
            "expenses": feed,
            "raw_people": roommates_data 
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)