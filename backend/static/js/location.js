document.querySelectorAll("[data-capture-location]").forEach((button) => {
    button.addEventListener("click", () => {
        const status = button.parentElement.querySelector("[data-location-status]");
        const latitudeInput = document.getElementById("id_latitude");
        const longitudeInput = document.getElementById("id_longitude");

        if (!navigator.geolocation) {
            status.textContent = "Location is not available in this browser. You can enter coordinates below.";
            return;
        }

        button.disabled = true;
        status.textContent = "Waiting for location permission…";
        navigator.geolocation.getCurrentPosition(
            (position) => {
                latitudeInput.value = position.coords.latitude.toFixed(6);
                longitudeInput.value = position.coords.longitude.toFixed(6);
                status.textContent = "Location added. You can adjust the coordinates before saving.";
                button.disabled = false;
            },
            (error) => {
                const messages = {
                    1: "Location permission was denied. Allow access in your browser settings or enter coordinates below.",
                    2: "Your device location could not be determined. Try again or enter coordinates below.",
                    3: "Location request timed out. Try again or enter coordinates below.",
                };
                status.textContent = messages[error.code] || "Could not get your location. You can enter coordinates below.";
                button.disabled = false;
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
        );
    });
});
