# 🚀 Desplegar a Firebase (Cloud Run + Hosting)

Guía para subir tu plataforma. Front en **Firebase Hosting**, backend FastAPI en
**Cloud Run**. Al terminar tendrás una URL pública que **sí** puede jalar cuotas
reales (soluciona el bloqueo de tu red de trabajo).

> ⏱️ Tiempo estimado: ~15 min la primera vez.
> 💳 Requiere plan **Blaze** (pago por uso). Para uso personal la capa gratis
> normalmente cubre todo → pagas $0 o centavos.

---

## Paso 0 — Requisitos (instalar una vez)

1. **Node.js** (para el Firebase CLI): <https://nodejs.org/>
2. **Firebase CLI:**
   ```bash
   npm install -g firebase-tools
   ```
3. **Google Cloud CLI (gcloud):** <https://cloud.google.com/sdk/docs/install>
4. Inicia sesión en ambos:
   ```bash
   firebase login
   gcloud auth login
   ```

---

## Paso 1 — Activar el plan Blaze

1. Entra a <https://console.firebase.google.com/> y abre tu proyecto
   (o crea uno con **Add project**).
2. Abajo a la izquierda verás tu plan → clic en **Upgrade** → elige **Blaze**.
3. Agrega una tarjeta. (Puedes ponerte un **presupuesto/alerta** en $1 USD para
   dormir tranquilo; el uso personal casi no consume.)

Anota tu **Project ID** (lo ves en Configuración del proyecto ⚙️). Lo necesitas abajo.

---

## Paso 2 — Configurar el proyecto local

En la carpeta `betting-platform`:

1. Edita `.firebaserc` y cambia `TU-PROJECT-ID` por tu Project ID real.
2. Apunta gcloud a tu proyecto:
   ```bash
   gcloud config set project TU-PROJECT-ID
   ```
3. Habilita las APIs necesarias (una sola vez):
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com
   ```

---

## Paso 3 — Desplegar el backend a Cloud Run

Desde la carpeta `betting-platform` (donde está el `Dockerfile`):

```bash
gcloud run deploy value-betting ^
  --source . ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --set-env-vars ODDS_API_KEY=a6fafbb2960f1bddd8e8fc4a5763c840,ODDS_REGIONS=us,eu,BANKROLL=100,MIN_EDGE=2.0,MIN_STAKE=10,MAX_STAKE_PCT=15
```

> En **PowerShell** usa acento grave ` en vez de `^` para partir líneas, o pon todo en una sola línea.
> El nombre del servicio **debe** ser `value-betting` (así lo espera `firebase.json`).
> La región **debe** ser `us-central1` (o cámbiala también en `firebase.json`).

Cuando termine te dará una **Service URL** (algo como
`https://value-betting-xxxx.a.run.app`). Ábrela: ya debería mostrar cuotas reales. ✅

### (Opcional, recomendado) Poner la API key como SECRETO en vez de env-var

```bash
echo -n "a6fafbb2960f1bddd8e8fc4a5763c840" | gcloud secrets create ODDS_API_KEY --data-file=-
gcloud run deploy value-betting --source . --region us-central1 --allow-unauthenticated ^
  --update-secrets ODDS_API_KEY=ODDS_API_KEY:latest ^
  --set-env-vars ODDS_REGIONS=us,eu,BANKROLL=100,MIN_STAKE=10,MAX_STAKE_PCT=15
```

### (Opcional) Proteger con clave de acceso

Agrega `,ACCESS_KEY=miclave123` a `--set-env-vars`. Luego abre la app con
`?k=miclave123` al final de la URL. Sin la clave, nadie podrá gastar tu cuota.

---

## Paso 4 — Desplegar el front a Firebase Hosting

```bash
firebase deploy --only hosting
```

Al terminar te da la **Hosting URL** (`https://TU-PROJECT-ID.web.app`).
¡Esa es tu app! El front vive ahí y llama al backend de Cloud Run por los rewrites.

---

## Actualizar después de cambios

- Cambiaste **Python/backend** → repite el Paso 3 (`gcloud run deploy ...`).
- Cambiaste **el front (web/index.html)** → repite el Paso 4 (`firebase deploy --only hosting`).

---

## Costos y límites (tranquilidad)

- Cloud Run: capa gratis de ~2 millones de requests/mes. Uso personal = $0.
- The Odds API (tier gratis): 500 requests/mes. Cada búsqueda gasta 1. Con la
  **clave de acceso** evitas que otros te la quemen.
- Ponte una alerta de presupuesto en Google Cloud Billing por si acaso.

---

## Problemas comunes

| Síntoma | Solución |
|---|---|
| `Billing account not configured` | Falta activar Blaze (Paso 1). |
| `serviceId not found` al hacer hosting deploy | Primero despliega Cloud Run (Paso 3) con el nombre `value-betting`. |
| El front carga pero dice "API offline" | Revisa que el `serviceId` y `region` en `firebase.json` coincidan con tu Cloud Run. |
| Sigue en modo DEMO en la nube | La env-var `ODDS_API_KEY` no llegó al Cloud Run. Revisa el `--set-env-vars`. |
