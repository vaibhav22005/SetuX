document.querySelectorAll("[data-hospital-directions]").forEach((button) => {
    button.addEventListener("click", () => {
        const status = button.parentElement.querySelector("[data-directions-status]");
        const latitude = button.dataset.hospitalLatitude;
        const longitude = button.dataset.hospitalLongitude;
        const hospitalMapUrl = `https://www.openstreetmap.org/?mlat=${encodeURIComponent(latitude)}&mlon=${encodeURIComponent(longitude)}&zoom=15`;
        const mapWindow = window.open("about:blank", "_blank");

        if (!mapWindow) {
            status.textContent = "Allow pop-ups to open the hospital map and directions.";
            return;
        }
        mapWindow.opener = null;

        const showHospitalMap = (message) => {
            mapWindow.location.replace(hospitalMapUrl);
            status.textContent = message;
        };

        if (!navigator.geolocation) {
            showHospitalMap("Location is unavailable in this browser; showing the hospital on the map.");
            return;
        }

        button.disabled = true;
        status.textContent = "Waiting for permission to use your location for directions…";
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const origin = `${position.coords.latitude},${position.coords.longitude}`;
                const destination = `${latitude},${longitude}`;
                const route = encodeURIComponent(`${origin};${destination}`);
                const directionsUrl = `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${route}`;
                mapWindow.location.replace(directionsUrl);
                status.textContent = "Directions opened. Your location was not saved to your profile.";
                button.disabled = false;
            },
            (error) => {
                const messages = {
                    1: "Location permission was denied; showing the hospital on the map instead.",
                    2: "Your location could not be determined; showing the hospital on the map instead.",
                    3: "Location request timed out; showing the hospital on the map instead.",
                };
                showHospitalMap(messages[error.code] || "Could not get your location; showing the hospital on the map instead.");
                button.disabled = false;
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
        );
    });
});
