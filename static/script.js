function createTrip() {
    alert("Let's plan a new trip!");
    let tripName = prompt("Where would you like to go?");
    if (tripName !== null) {
        alert("Destination: " + tripName);
    }
}
