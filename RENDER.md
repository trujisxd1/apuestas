# 🚀 Desplegar en Render.com (gratis, sin tarjeta)

Render corre tu FastAPI (front + backend en un solo servicio) usando el `Dockerfile`.
Al terminar tendrás una URL pública que **sí** jala cuotas reales (soluciona el bloqueo
de tu red de trabajo).

> ⏱️ ~10 min. 💳 Sin tarjeta. El plan free se **duerme** tras 15 min sin uso:
> la primera carga tras dormir tarda ~30-60 seg. Para uso personal, no importa.

---

## Cómo funciona

Render despliega desde un **repositorio Git** (GitHub). O sea, el flujo es:
subes el código a GitHub → conectas el repo en Render → Render construye el
`Dockerfile` y te da la URL. Tu API key va como **variable secreta en Render**,
nunca en el código (el `.gitignore` ya protege tu `.env`).

---

## Paso 1 — Subir el código a GitHub

1. Crea una cuenta gratis en <https://github.com/> si no tienes.
2. Crea un repositorio nuevo (botón **New**), por ejemplo `value-betting`.
   Puede ser **privado** (recomendado).
3. En tu compu, dentro de la carpeta `betting-platform`:
   ```bash
   git init
   git add .
   git commit -m "Plataforma de value betting"
   git branch -M main
   git remote add origin https://github.com/TU-USUARIO/value-betting.git
   git push -u origin main
   ```

> ✅ Tu `.env` con la API key **NO** se sube (está en `.gitignore`). Bien.

---

## Paso 2 — Crear el servicio en Render

1. Entra a <https://render.com/> y regístrate (puedes usar tu cuenta de GitHub).
2. Clic en **New +** → **Blueprint**.
3. Conecta tu repo `value-betting`. Render detecta el `render.yaml` solo.
4. Clic en **Apply**. Empezará a construir el Docker (tarda unos minutos la 1ª vez).

### Opción manual (si prefieres sin Blueprint)

**New +** → **Web Service** → conecta el repo → Render detecta el `Dockerfile`.
Elige plan **Free**, región **Oregon**, y en *Health Check Path* pon `/info`.

---

## Paso 3 — Poner tu API key (secreta)

En el servicio, ve a la pestaña **Environment** y agrega:

| Key | Value |
|---|---|
| `ODDS_API_KEY` | `a6fafbb2960f1bddd8e8fc4a5763c840` |
| `ACCESS_KEY` *(opcional)* | una clave tuya, ej. `gustavo2026` |

Guarda. Render redepliega solo. (Las demás variables ya vienen del `render.yaml`.)

---

## Paso 4 — ¡Listo!

Render te da una URL tipo `https://value-betting.onrender.com`.
Ábrela → verás el panel con **cuotas reales**. 🎉

- Si pusiste `ACCESS_KEY`, ábrela así: `https://value-betting.onrender.com/?k=gustavo2026`
- Guárdala en favoritos de tu celular para usarla junto a Caliente.

---

## Actualizar después

Cualquier cambio: `git add . && git commit -m "..." && git push`.
Render lo detecta y redepliega solo (por `autoDeploy: true`).

---

## Problemas comunes

| Síntoma | Solución |
|---|---|
| Sigue en modo DEMO | Falta la variable `ODDS_API_KEY` en *Environment* (Paso 3). |
| "Application failed to respond" | Espera: puede estar despertando del sueño (~1 min). Recarga. |
| Build falla | Revisa que `Dockerfile` y `requirements.txt` estén en la raíz del repo. |
| 401 al buscar value | Tienes `ACCESS_KEY` puesta; abre la app con `?k=tuclave`. |
