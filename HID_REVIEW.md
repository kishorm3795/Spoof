# HID Hackathon review prototype

This branch adds an optional active-liveness kiosk page without changing the existing PCA recognition backend or its stored data.

## Run

1. Install the existing backend dependencies: `pip install -r requirements.txt`.
2. Start the API from the backend directory: `uvicorn main:app --host 127.0.0.1 --port 8000`.
3. In a second terminal, serve the frontend directory: `python -m http.server 5500`.
4. Open `http://localhost:5500/kiosk.html`.
5. Register at least two identities through the existing application before testing recognition, because the current PCA implementation requires at least two enrolled faces.
6. Allow webcam access, start the camera, then begin authentication.

The kiosk loads MediaPipe Tasks Vision and its Face Landmarker model from public CDNs, so the browser needs internet access on first load. The API URL is currently `http://localhost:8000`; change the `API` constant in `frontend/kiosk.html` if the API runs elsewhere.

## What this prototype demonstrates

- Random blink or head-turn challenge using browser-side facial landmarks.
- Identity verification by calling the existing `POST /verify` endpoint.
- Combined demonstration outcome: a passed challenge followed by a recognized identity yields `ALLOW`; a failed identity match yields `DENY`.
- Elapsed time from challenge start through challenge completion and identity API response.

## Security and evaluation limitations

- This is an active-challenge demonstration, not a trained passive presentation-attack detector (PAD).
- Landmark checks execute in the browser and are not trusted security evidence; a manipulated client can bypass them.
- A blink/head-turn challenge does not establish robust protection against printed photos, screen/video replay, or 3D masks. Physical attack testing and a server-side PAD model are still required.
- The elapsed time includes the human challenge duration. Do not claim that the complete challenge flow meets the 2-second requirement based on this prototype. Measure the initial decision path separately and report actual p50/p95 latency.
- The existing PCA recognizer is retained unchanged for this review. Its accuracy and security have not been independently validated by this change.
- The existing backend's permissive CORS and unauthenticated enrollment/deletion routes are not suitable for production deployment. Keep this prototype local and do not expose it publicly.

## Next engineering iteration

Benchmark a properly licensed deep face-recognition model and a server-side ONNX PAD model on the target AWS instance. Evaluate APCER/BPCER using genuine and attack presentations, and only claim results measured on the test protocol.
