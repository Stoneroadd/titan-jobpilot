# TITAN JobPilot

Asistente local en Python para organizar ofertas de trabajo, comparar requisitos contra habilidades declaradas y preparar formularios de postulación con autollenado por navegador.

**El agente automatiza la preparación; la persona revisa cada formulario y decide si enviarlo.** JobPilot no busca en portales por scraping, no envía solicitudes sin una acción humana y no elude CAPTCHA, controles anti-bot, autenticación ni términos de los sitios.

## Funciones del MVP

- Perfil editable y CV PDF/DOCX guardados en `data/private/` (máximo 10 MB).
- Captura manual de ofertas o importación desde CSV.
- Detección de duplicados por URL o combinación empresa/cargo.
- Afinidad reproducible por coincidencia literal entre habilidades del perfil y de la oferta.
- Pipeline con estados Nueva, En revisión, Postulada y Descartada.
- Playwright abre la URL oficial configurada, rellena campos comunes y adjunta el CV si identifica un único campo de archivo.
- Acción individual o preparación secuencial de las ofertas marcadas En revisión.
- Pausa de revisión en cada oferta. La persona puede inspeccionar, editar, adjuntar lo que falte y enviar manualmente.
- Formularios locales con token CSRF; el servidor escucha solo en `127.0.0.1`.

## Instalación

Requiere Python 3.10 o posterior.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Abre `http://127.0.0.1:5055`. Guarda tu perfil, carga un CV, añade ofertas o importa `static/offers.example.csv`, y configura la URL oficial del formulario.

Para iniciar la cola, cambia a **En revisión** las ofertas que quieras preparar y pulsa **Preparar cola**. El agente las abre una por una en Chromium; comprueba dominio, empresa, cargo, campos y documento antes de enviar cada solicitud manualmente. Pulsa Enter en la consola para pasar a la siguiente oferta.

En Linux/macOS activa el entorno con `source .venv/bin/activate`. El puerto se cambia con `JOBPILOT_PORT`; el directorio privado puede moverse definiendo `JOBPILOT_DATA_DIR` antes de iniciar la app.

## Privacidad y seguridad

- La copia del repositorio contiene solo código y ofertas ficticias. Datos del candidato, ofertas locales y CV se guardan en `data/private/`, excluida por `.gitignore`.
- Mantén el servidor ligado a localhost. No lo expongas a una LAN ni a internet; este prototipo no implementa cuentas, cifrado en reposo ni multiusuario.
- Un formulario puede enviar el CV y datos personales al dominio que configures cuando tú confirmes manualmente el envío. Revisa que la URL sea auténtica y consulta la política del empleador.
- No guardes contraseñas de portales en la app. Inicia sesión tú mismo cuando la web lo pida.
- El autollenado heurístico puede equivocarse o dejar campos sin completar. Revisa el resultado de cada formulario.
- Si detecta un CAPTCHA, el agente se detiene y no intenta resolverlo. Los controles anti-bot, MFA, accesos y límites del portal deben respetarse.
- El botón de cola prepara formularios, pero no hace clic en “Enviar”, no firma declaraciones y no marca automáticamente que una postulación fue enviada.

## CSV

Encabezados requeridos: `title`, `company`. Campos opcionales: `location`, `application_url`, `description`, `skills`. `skills` acepta habilidades separadas por `;` o `,`. No se descargan ofertas de forma automática; el usuario configura las fuentes y revisa cada oferta.

## Límites conocidos

Los formularios de cada empresa difieren; el autollenado cubre patrones comunes de nombre, correo, teléfono, ubicación, LinkedIn, portafolio y CV. No adapta respuestas extensas, preguntas de elegibilidad, salario esperado ni declaraciones legales. No es un sistema de seguimiento laboral ni una integración oficial con portales. Una coincidencia de habilidades no predice la probabilidad de contratación.

## Licencia

MIT. Consulta [`LICENSE`](LICENSE).
