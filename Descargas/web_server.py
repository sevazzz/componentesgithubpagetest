import os
import math
import time
import asyncio
import serial
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

PUERTO_COM = "COM3" 
try:
    arduino = serial.Serial(PUERTO_COM, 9600, timeout=0.1)
    time.sleep(2)
    print(f"✅ Comunicación Serial establecida en {PUERTO_COM}")
except Exception as e:
    print(f"❌ Error al abrir el puerto {PUERTO_COM}: {e}")
    arduino = None

clientes_conectados = set()
escaneo_continuo = False
ultima_lectura_tiempo = time.time()

html_content = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radar Táctico Web - UNAB</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #F2F2F2;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            background-color: #173864;
            box-shadow: 0 4px 12px rgba(23, 56, 100, 0.2);
        }
        .card-radar {
            border: 2px solid #B4C7D9 !important;
            background-color: #FFFFFF;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.05);
        }
        .canvas-container {
            background-color: #000000;
            padding: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        canvas {
            display: block;
            max-width: 100%;
            height: auto;
        }
        .btn-unab {
            background-color: #173864;
            color: #FFFFFF;
            border: 1px solid #173864;
            font-weight: 600;
            letter-spacing: 0.5px;
            padding: 12px 30px;
            transition: all 0.3s ease;
        }
        .btn-unab:hover {
            background-color: #FFFFFF;
            color: #173864;
            border-color: #173864;
            box-shadow: 0 4px 12px rgba(23, 56, 100, 0.15);
        }
        .form-select-unab {
            border: 2px solid #B4C7D9;
            color: #173864;
            font-weight: 600;
        }
        .form-select-unab:focus {
            border-color: #173864;
            box-shadow: 0 0 0 0.25rem rgba(23, 56, 100, 0.25);
        }
        .telemetria-box {
            background-color: #FFFFFF;
            color: #173864;
            border: 1px solid #B4C7D9;
            font-family: 'Courier New', Courier, monospace;
            font-weight: bold;
            font-size: 0.95rem;
        }
    </style>
</head>
<body>

    <header class="text-white text-center py-3 mb-4">
        <div class="container">
            <h1 class="h4 m-0 text-uppercase fw-bold">
                <i class="fa-solid fa-satellite-dish me-2"></i> Sistema Táctico Radar - Interfaz Distribuida
            </h1>
        </div>
    </header>

    <div class="container flex-grow-1 d-flex align-items-center py-3">
        <div class="row justify-content-center w-100 m-0">
            <div class="col-12 col-md-10 col-lg-8 p-0">
                
                <div class="card card-radar">
                    <div class="canvas-container">
                        <canvas id="radarCanvas" width="700" height="420"></canvas>
                    </div>
                    
                    <div class="card-body p-4 bg-light border-top" style="border-color: #B4C7D9 !important;">
                        <div class="row g-3 align-items-center justify-content-center mb-3">
                            <div class="col-12 col-sm-6">
                                <div class="input-group">
                                    <span class="input-group-text bg-white text-secondary" style="border-color: #B4C7D9;"><i class="fa-solid fa-eye"></i></span>
                                    <select id="selectVista" class="form-select form-select-unab text-uppercase">
                                        <option value="1" selected>Modo 1: Punto con Sombra</option>
                                        <option value="2">Modo 2: Arcos de Impacto</option>
                                        <option value="3">Modo 3: Retícula Táctica</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-12 col-sm-6 text-sm-start text-center">
                                <button id="btnEscaneo" class="btn btn-unab text-uppercase shadow-sm w-100 py-2">
                                    <i class="fa-solid fa-play me-2"></i> Iniciar Escaneo Continuo
                               </button>
                            </div>
                        </div>
                        
                        <div id="telemetria" class="telemetria-box p-3 rounded shadow-sm text-center">
                            <i class="fa-solid fa-gear fa-spin me-2"></i> ESTADO: CONFIGURANDO SISTEMA...
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('radarCanvas');
        const ctx = canvas.getContext('2d');
        const btnEscaneo = document.getElementById('btnEscaneo');
        const selectVista = document.getElementById('selectVista');
        const divTelemetria = document.getElementById('telemetria');

        const CENTRO_X = canvas.width / 2;
        const CENTRO_Y = canvas.height - 30;
        const RADIO_MAX = 360;
        const MAX_DISTANCIA_CM = 40.0;

        let historialRadar = {};
        let anguloActual = 0;
        let distanciaActual = 0;
        let escaneando = false; 
        let modoVistaActivo = 1;

        const COLOR_GRID_BASE = "rgba(0, 80, 120, 0.3)";
        const COLOR_GRID_TEXT = "rgba(0, 120, 150, 0.7)";
        const COLOR_TEXTO = "#00ffff";
        const COLOR_BARRIDO = "#00c8ff";
        const COLOR_OBSTACULO = "#ff0000";

        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const socket = new WebSocket(wsProtocol + window.location.host + "/ws");

        socket.onopen = () => {
            divTelemetria.innerHTML = '<i class="fa-solid fa-circle-check text-success me-2"></i> ESTADO: EN LÍNEA - CONECTADO AL SERVIDOR';
        };

        socket.onmessage = (event) => {
            const datos = event.data.split(",");
            if(datos.length === 2) {
                anguloActual = parseInt(datos[0]);
                distanciaActual = parseFloat(datos[1]);
                
                historialRadar[anguloActual] = distanciaActual;
                divTelemetria.innerHTML = `<i class="fa-solid fa-bullseye fa-pulse text-danger me-2"></i> AZIMUTH: ${anguloActual} DEG | DISTANCIA: ${distanciaActual.toFixed(1)} CM`;
                
                dibujarRadar();
            }
        };

        socket.onclose = () => {
            divTelemetria.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-danger me-2"></i> ESTADO: DESCONECTADO - INTERRUPCIÓN DE ENLACE';
            resetBoton();
        };

        selectVista.onchange = () => {
            modoVistaActivo = parseInt(selectVista.value);
            dibujarRadar();
        };

        btnEscaneo.onclick = () => {
            if(socket.readyState === WebSocket.OPEN) {
                if (!escaneando) {
                    socket.send("START");
                    escaneando = true;
                    btnEscaneo.innerHTML = '<i class="fa-solid fa-stop me-2"></i> Detener Escaneo';
                    btnEscaneo.className = "btn btn-danger text-uppercase shadow-sm w-100 py-2";
                    divTelemetria.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i> ESTADO: ACTIVANDO BARRIDO INDEFINIDO...';
                } else {
                    socket.send("STOP");
                    resetBoton();
                    divTelemetria.innerHTML = '<i class="fa-solid fa-circle-info text-primary me-2"></i> ESTADO: ESCANEO DETENIDO';
                }
            }
        };

        function resetBoton() {
            escaneando = false;
            btnEscaneo.innerHTML = '<i class="fa-solid fa-play me-2"></i> Iniciar Escaneo Continuo';
            btnEscaneo.className = "btn btn-unab text-uppercase shadow-sm w-100 py-2";
        }

        function dibujarRadar() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const escalas = [RADIO_MAX/4, RADIO_MAX/2, (RADIO_MAX*3)/4, RADIO_MAX];
            const etiquetas = ["10cm", "20cm", "30cm", "40cm"];
            
            escalas.forEach((r, idx) => {
                ctx.beginPath();
                ctx.arc(CENTRO_X, CENTRO_Y, r, Math.PI, 0);
                ctx.strokeStyle = COLOR_GRID_BASE;
                ctx.lineWidth = 1;
                ctx.stroke();

                ctx.fillStyle = COLOR_GRID_TEXT;
                ctx.font = "10px monospace";
                ctx.fillText(etiquetas[idx], CENTRO_X + 10, CENTRO_Y - r + 4);
            });

            const angulosGrid = [30, 60, 90, 120, 150];
            angulosGrid.forEach(a => {
                let rad = (a * Math.PI) / 180;
                let x = CENTRO_X + RADIO_MAX * Math.cos(rad);
                let y = CENTRO_Y - RADIO_MAX * Math.sin(rad);

                ctx.beginPath();
                ctx.moveTo(CENTRO_X, CENTRO_Y);
                ctx.lineTo(x, y);
                ctx.strokeStyle = COLOR_GRID_BASE;
                ctx.stroke();

                ctx.fillText(a + "°", x + (x < CENTRO_X ? -25 : 5), y - 2);
            });

            for (let antiguoAng in historialRadar) {
                let antiguoDist = historialRadar[antiguoAng];
                if (antiguoDist >= MAX_DISTANCIA_CM) continue;

                let radObstaculo = (antiguoAng * Math.PI) / 180;
                let numCapasSombra = 3;
                let decalajeCm = 1.3;

                if (modoVistaActivo === 1) {
                    for (let i = 1; i <= numCapasSombra; i++) {
                        let rCapa = antiguoDist + (i * decalajeCm);
                        if (rCapa < MAX_DISTANCIA_CM) {
                            let rPxCapa = (rCapa / MAX_DISTANCIA_CM) * RADIO_MAX;
                            let sx = CENTRO_X + rPxCapa * Math.cos(radObstaculo);
                            let sy = CENTRO_Y - rPxCapa * Math.sin(radObstaculo);

                            let opacidad = 0.5 - (i * 0.15);
                            ctx.beginPath();
                            ctx.arc(sx, sy, 3, 0, 2 * Math.PI);
                            ctx.fillStyle = `rgba(255, 0, 0, ${opacidad})`;
                            ctx.fill();
                        }
                    }
                    let rPixelFrente = (antiguoDist / MAX_DISTANCIA_CM) * RADIO_MAX;
                    let ox = CENTRO_X + rPixelFrente * Math.cos(radObstaculo);
                    let oy = CENTRO_Y - rPixelFrente * Math.sin(radObstaculo);

                    ctx.beginPath();
                    ctx.arc(ox, oy, 5, 0, 2 * Math.PI);
                    ctx.fillStyle = COLOR_OBSTACULO;
                    ctx.fill();

                } else if (modoVistaActivo === 2) {
                    for (let i = 1; i <= numCapasSombra; i++) {
                        let rCapa = antiguoDist + (i * decalajeCm);
                        if (rCapa < MAX_DISTANCIA_CM) {
                            let rPxCapa = (rCapa / MAX_DISTANCIA_CM) * RADIO_MAX;
                            let opacidad = 0.4 - (i * 0.12);
                            ctx.beginPath();
                            ctx.arc(CENTRO_X, CENTRO_Y, rPxCapa, -radObstaculo - 0.05, -radObstaculo + 0.05);
                            ctx.strokeStyle = `rgba(255, 0, 0, ${opacidad})`;
                            ctx.lineWidth = 4;
                            ctx.stroke();
                        }
                    }
                    let rPxFrente = (antiguoDist / MAX_DISTANCIA_CM) * RADIO_MAX;
                    ctx.beginPath();
                    ctx.arc(CENTRO_X, CENTRO_Y, rPxFrente, -radObstaculo - 0.05, -radObstaculo + 0.05);
                    ctx.strokeStyle = COLOR_OBSTACULO;
                    ctx.lineWidth = 6;
                    ctx.stroke();

                } else if (modoVistaActivo === 3) {
                    for (let i = 1; i <= numCapasSombra; i++) {
                        let rCapa = antiguoDist + (i * decalajeCm);
                        if (rCapa < MAX_DISTANCIA_CM) {
                            let rPxCapa = (rCapa / MAX_DISTANCIA_CM) * RADIO_MAX;
                            let sx = CENTRO_X + rPxCapa * Math.cos(radObstaculo);
                            let sy = CENTRO_Y - rPxCapa * Math.sin(radObstaculo);
                            let opacidad = 0.4 - (i * 0.12);
                            ctx.beginPath();
                            ctx.arc(sx, sy, 3, 0, 2 * Math.PI);
                            ctx.fillStyle = `rgba(255, 0, 0, ${opacidad})`;
                            ctx.fill();
                        }
                    }
                    let rPxFrente = (antiguoDist / MAX_DISTANCIA_CM) * RADIO_MAX;
                    let ox = CENTRO_X + rPxFrente * Math.cos(radObstaculo);
                    let oy = CENTRO_Y - rPxFrente * Math.sin(radObstaculo);
                    
                    ctx.beginPath();
                    ctx.arc(ox, oy, 3, 0, 2 * Math.PI);
                    ctx.fillStyle = COLOR_OBSTACULO;
                    ctx.fill();
                    
                    ctx.beginPath();
                    ctx.moveTo(ox - 8, oy); ctx.lineTo(ox + 8, oy);
                    ctx.moveTo(ox, oy - 8); ctx.lineTo(ox, oy + 8);
                    ctx.strokeStyle = COLOR_OBSTACULO;
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                }
            }

            let radActual = (anguloActual * Math.PI) / 180;
            let lx = CENTRO_X + RADIO_MAX * Math.cos(radActual);
            let ly = CENTRO_Y - RADIO_MAX * Math.sin(radActual);

            ctx.beginPath();
            ctx.moveTo(CENTRO_X, CENTRO_Y);
            ctx.lineTo(lx, ly);
            ctx.strokeStyle = COLOR_BARRIDO;
            ctx.lineWidth = 3;
            ctx.stroke();
        }

        dibujarRadar();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return html_content

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global escaneo_continuo, ultima_lectura_tiempo
    await websocket.accept()
    clientes_conectados.add(websocket)
    print(f"📱 Dispositivo en línea conectado al Radar. Total clientes: {len(clientes_conectados)}")
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                if data == "START":
                    escaneo_continuo = True
                    ultima_lectura_tiempo = time.time()
                    if arduino:
                        arduino.write(b'S')
                        arduino.reset_input_buffer()
                elif data == "STOP":
                    escaneo_continuo = False
                    print("🛑 Escaneo continuo pausado por el usuario.")
            except asyncio.TimeoutError:
                pass

            ahora = time.time()
            if escaneo_continuo and (ahora - ultima_lectura_tiempo > 0.35):
                if arduino:
                    arduino.write(b'S')
                    arduino.reset_input_buffer()
                ultima_lectura_tiempo = ahora 

            if arduino and arduino.in_waiting > 0:
                linea = arduino.readline().decode('utf-8', errors='ignore').strip()
                if "," in linea:
                    ultima_lectura_tiempo = time.time() 
                    for cliente in list(clientes_conectados):
                        try:
                            await cliente.send_text(linea)
                        except Exception:
                            clientes_conectados.remove(cliente)
            
            await asyncio.sleep(0.005)

    except WebSocketDisconnect:
        clientes_conectados.remove(websocket)
        print(f"❌ Dispositivo desconectado. Total clientes: {len(clientes_conectados)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)