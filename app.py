from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    trip_name = None
    destination = None
    if request.method == "POST":
        print("A form was submitted!")
        trip_name = request.form.get("trip-name")
        print(f"Trip Name: {trip_name}")
        destination = request.form.get("destination")
        print(f"Destination: {destination}")
    
    return render_template("index.html", trip_name=trip_name, destination=destination)

