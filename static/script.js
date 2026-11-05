
const tripDialog = document.getElementById("new-trip-dialog");
const newTripButton = document.getElementById("new-trip-btn");
const emptyNewTripButton = document.getElementById("empty-new-trip-btn");
const closeTripButton = document.getElementById("close-trip-btn");
const cancelTripButton = document.getElementById("cancel-trip-btn");
const tripNameInput = document.getElementById("trip-name");
const tripForm = tripDialog.querySelector("form");

function openTripDialog() {
    routeSearch++;
    tripForm.reset();
    document.getElementById('route-place-results').replaceChildren();
    tripDialog.showModal();
    tripNameInput.focus();
}

function closeTripDialog() {
    routeSearch++;
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


for (const input of document.querySelectorAll('[data-confirm-name]')) {
    input.addEventListener('input', () => {
        input.setCustomValidity(input.value.trim() === input.dataset.confirmName.trim() ? '' : 'Type the trip name exactly to confirm deletion.');
    });
}

const routeStopsInput = document.getElementById('route-stops');
const routePlaces = document.getElementById('setup-places');
const routeResults = document.getElementById('route-place-results');
let routeSearch = 0;
routeStopsInput.addEventListener('input', () => {
    routeSearch++;
    routeResults.replaceChildren();
    routePlaces.value = '{}';
});
document.getElementById('find-route-places').addEventListener('click', async () => {
    const search = ++routeSearch;
    const names = [...new Set(routeStopsInput.value.split('\n').map(line => line.split('|')[0].trim()).filter(Boolean))];
    if (!names.length || names.length > 50) {
        routeResults.textContent = 'Enter 1 to 50 stops first.';
        return;
    }
    routeResults.textContent = 'Looking up places…';
    routePlaces.value = '{}';
    const chosen = {};
    const container = document.createElement('div');
    for (const name of names) {
        if (search !== routeSearch) return;
        const label = document.createElement('label');
        label.textContent = name;
        try {
            const response = await fetch('/api/places?name=' + encodeURIComponent(name));
            if (!response.ok) throw Error('Search unavailable');
            const data = await response.json();
            const select = document.createElement('select');
            select.add(new Option(data.results.length ? 'Choose the matching place' : 'No match — add a map location later', ''));
            data.results.forEach((place, index) => select.add(new Option(place.label, String(index))));
            select.addEventListener('change', () => {
                if (select.value === '') delete chosen[name];
                else chosen[name] = data.results[Number(select.value)];
                routePlaces.value = JSON.stringify(chosen);
            });
            label.append(select);
        } catch (_) {
            const note = document.createElement('p');
            note.textContent = 'Search unavailable. You can create this stop and find its map location later.';
            label.append(note);
        }
        container.append(label);
    }
    if (search === routeSearch) routeResults.replaceChildren(container);
});
