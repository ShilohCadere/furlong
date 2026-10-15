
const tripDialog = document.getElementById("new-trip-dialog");
const newTripButton = document.getElementById("new-trip-btn");
const emptyNewTripButton = document.getElementById("empty-new-trip-btn");
const closeTripButton = document.getElementById("close-trip-btn");
const cancelTripButton = document.getElementById("cancel-trip-btn");
const tripNameInput = document.getElementById("trip-name");
const tripForm = tripDialog.querySelector("form");

function openTripDialog() {
    tripForm.reset();
    tripDialog.showModal();
    tripNameInput.focus();
}

function closeTripDialog() {
    tripDialog.close();
}

newTripButton.addEventListener("click", openTripDialog);
closeTripButton.addEventListener("click", closeTripDialog);
cancelTripButton.addEventListener("click", closeTripDialog);

if (emptyNewTripButton) {
    emptyNewTripButton.addEventListener("click", openTripDialog);
}

// Close when clicking the backdrop, not the dialog content.
tripDialog.addEventListener("click", function(event) {
    if (event.target === tripDialog) {
        closeTripDialog();
    }
});
