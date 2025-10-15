# 📱 I-Tec NFC Scanner System

**Sistema completo de gestión de activos con tecnología NFC avanzada** - Incluye aplicación móvil Android, API REST optimizada y dashboard web con análisis inteligente en tiempo real.

## 🚀 Características Principales

### 📱 **Aplicación Móvil Nativa**
- ✅ **Lectura NFC real** con hardware del dispositivo
- ✅ **Análisis inteligente** de contenido (URLs, emails, Asset IDs, JSON)
- ✅ **Scanner QR/Códigos de barras** integrado
- ✅ **Configuración dinámica** de servidor
- ✅ **Envío automático** al servidor con retry
- ✅ **Interfaz Ionic moderna** y responsive

### 🖥️ **Servidor Flask Avanzado**
- ✅ **API REST completa** con endpoints especializados
- ✅ **Procesamiento inteligente** de datos NFC
- ✅ **WebSockets** para actualizaciones tiempo real
- ✅ **Análisis de seguridad** automático
- ✅ **Base de datos SQLite** optimizada
- ✅ **CORS configurado** para múltiples orígenes

### 🌐 **Dashboard Web Responsive**
- ✅ **Panel principal** con estadísticas en vivo
- ✅ **Tiempo real** via WebSockets
- ✅ **Historial completo** con filtros avanzados
- ✅ **Interfaz móvil** optimizada para navegadores
- ✅ **Visualización inteligente** de tipos de contenido

## 🏗️ Arquitectura del Sistema

```
┌─────────────────┐    HTTP/API    ┌──────────────────┐    WebSocket    ┌─────────────────┐
│   📱 App Móvil  │ ──────────────► │  🖥️ Servidor    │ ──────────────► │  🌐 Dashboard   │
│                 │                │     Flask        │                │      Web        │
│ • NFC Scanner   │                │                  │                │                 │
│ • QR/Barcode    │                │ • API REST       │                │ • Tiempo Real   │
│ • Config GUI    │                │ • Análisis IA    │                │ • Estadísticas  │
│ • Auto-envío    │                │ • Seguridad      │                │ • Historial     │
└─────────────────┘                │ • WebSockets     │                │ • Filtros       │
                                   └──────────────────┘                └─────────────────┘
                                            │
                                            ▼
                                   ┌──────────────────┐
                                   │  💾 SQLite DB    │
                                   │                  │
                                   │ • Lecturas NFC   │
                                   │ • Análisis IA    │
                                   │ • Metadatos      │
                                   │ • Estadísticas   │
                                   └──────────────────┘
```

## 📋 Características

### 📱 **Aplicación Móvil (Android)**
- ✅ **Lectura NFC real** usando hardware del dispositivo
- ✅ **Scanner QR/Códigos de barras** con cámara
- ✅ **Configuración dinámica** de servidor
- ✅ **Auto-detección de red** para múltiples IPs
- ✅ **Interfaz Ionic moderna** con tabs intuitivas
- ✅ **Envío automático** de datos al servidor

### 🖥️ **Servidor Backend (Flask)**
- ✅ **API REST completa** con endpoints especializados
- ✅ **Base de datos SQLite** para persistencia
- ✅ **WebSockets** para actualizaciones en tiempo real
- ✅ **CORS configurado** para conexiones móviles
- ✅ **Múltiples formatos** (NFC, QR, Barcode)

### 🌐 **Dashboard Web**
- ✅ **Panel principal** con estadísticas generales
- ✅ **Tiempo real** via WebSockets
- ✅ **Historial completo** de todas las lecturas
- ✅ **Interfaz responsiva** compatible con móviles
- ✅ **Página móvil optimizada** para navegadores

## 📂 Estructura del Proyecto (REORGANIZADA)

```
E:\I-Tec\
├── 📁 server/                          # 🖥️ Servidor Flask Backend
│   ├── 📄 app.py                       # Aplicación Flask principal
│   ├── 📄 improved_nfc_handler.py      # Procesador NFC avanzado con IA
│   ├── 📄 nfc_config.json              # Configuración centralizada
│   ├── 📄 requirements.txt             # Dependencias Python
│   ├── 📄 schema.sql                   # Esquema base de datos
│   ├── 📄 nfc_readings.db              # Base de datos SQLite
│   ├── 📁 templates/                   # Plantillas HTML
│   │   ├── dashboard.html              # Panel principal
│   │   ├── history.html                # Historial
│   │   ├── realtime_dashboard.html     # Dashboard tiempo real
│   │   └── mobile.html                 # Interfaz móvil web
│   └── 📁 static/                      # CSS, JS, imágenes
│
├── 📁 mobile/                          # 📱 Aplicación Móvil
│   ├── 📄 package.json                 # Dependencias Node.js
│   ├── 📄 capacitor.config.ts          # Configuración Capacitor
│   ├── 📄 compile-app.ps1              # ⚡ Script compilación automática
│   ├── 📁 src/                         # Código fuente Angular
│   │   ├── 📁 app/
│   │   │   ├── 📁 services/             # API & NFC con análisis IA
│   │   │   ├── 📁 tab1/                # Scanner NFC principal
│   │   │   ├── 📁 tab2/                # QR/Barcode scanner
│   │   │   └── 📁 tab3/                # Configuración servidor
│   │   └── 📁 environments/            # Config desarrollo/producción
│   ├── 📁 android/                     # Proyecto Android Capacitor
│   └── 📁 www/                         # Build compilado
│
├── 📁 releases/                        # 📦 APKs y Versiones
│   └── 📄 I-Tec-NFC-Scanner-v*.apk    # Versiones compiladas
│
├── 📁 docs/                            # 📚 Documentación
│   ├── 📄 INSTALL_INTEGRATION.md      # Guía instalación completa
│   ├── 📄 API_DOCUMENTATION.md        # Documentación API REST
│   ├── 📄 USER_GUIDE.md               # Manual de usuario
│   └── 📄 DEVELOPMENT.md              # Guía desarrolladores
│
├── 📄 README.md                        # 📖 Documentación principal
└── 📄 PROJECT_STRUCTURE.md            # 🗂️ Estructura detallada
```

### 🎯 **Rutas de Acceso Actualizadas**
- **Servidor**: `E:\I-Tec\server\app.py`
- **App Móvil**: `E:\I-Tec\mobile\compile-app.ps1`
- **Documentación**: `E:\I-Tec\docs\`
- **Releases**: `E:\I-Tec\releases\`

## 🚀 Instalación y Configuración

### 📋 **Requisitos Previos**

#### En el Servidor (PC):
- 🐍 **Python 3.10+** con pip
- 🌐 **Conexión a red local**
- 🔥 **Puertos 5001 libres**

#### Para Desarrollo Móvil:
- 📱 **Node.js 20.19+** y npm
- ⚡ **Ionic CLI** (`npm install -g @ionic/cli`)
- 🤖 **Android Studio** con SDK configurado
- 📱 **Dispositivo Android** con NFC habilitado

### 1️⃣ **Instalación del Servidor**

```bash
# 1. Navegar al directorio del servidor
cd E:\I-Tec\server

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Instalar dependencias adicionales si no están
pip install flask flask-cors flask-socketio

# 4. Iniciar servidor
python app.py
```

El servidor estará disponible en:
- 🌐 **Panel Web**: `http://tu-ip:5001`
- 📡 **API Health**: `http://tu-ip:5001/api/health`
- 📊 **Dashboard**: `http://tu-ip:5001/dashboard`

### 2️⃣ **Configuración de la App Móvil**

```bash
# 1. Navegar al proyecto móvil
cd E:\I-Tec\mobile

# 2. Instalar dependencias (puede tomar tiempo)
npm install --legacy-peer-deps

# 3. Configurar tu IP en el environment
# Editar: src/environments/environment.ts
# Cambiar: apiUrl: 'http://TU_IP_LOCAL:5001/api'
```

### 3️⃣ **Compilación para Android**

```bash
# 1. Generar build de la app
node build_manual.js

# 2. Sincronizar con Capacitor
npx cap sync android

# 3. Compilar APK
cd android
./gradlew assembleDebug

# 4. Instalar en dispositivo (con USB debugging)
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 4️⃣ **Configuración de Red**

#### **Obtener tu IP local:**
```bash
# En Windows (PowerShell)
ipconfig | findstr IPv4

# En Linux/Mac
ifconfig | grep inet
```

#### **Configurar firewall (Windows):**
```bash
# Permitir tráfico en puerto 5001
netsh advfirewall firewall add rule name="I-Tec NFC Server" dir=in action=allow protocol=TCP localport=5001
```

## 📱 Uso del Sistema

### **🖥️ Desde el Panel Web**

1. **Abrir navegador** en `http://tu-ip:5001`
2. **Ver estadísticas** en tiempo real
3. **Consultar historial** de todas las lecturas
4. **Monitorear** conexiones activas

### **📱 Desde la App Móvil**

1. **Abrir app "scanner"** en tu dispositivo Android
2. **Configurar servidor**:
   - Ve a la **Tab Configuración**
   - Ingresa: `http://tu-ip:5001/api`
   - Presiona **"Guardar y Probar"**
3. **Usar NFC**:
   - Ve a la **Tab Scanner**
   - Presiona **"Start NFC Scan"**
   - **Acerca un tag NFC** al dispositivo
   - Los datos se envían **automáticamente** al servidor

### **🌐 Desde Navegador Móvil**

Si no tienes la app instalada:
1. **Abrir navegador** en tu teléfono
2. **Ir a**: `http://tu-ip:5001/mobile`
3. **Usar simuladores** de NFC y QR

## 🔧 Configuración en Red Privada

### **Paso 1: Configurar el Servidor**

```python
# En app.py - Ya configurado por defecto
socketio.run(app, 
    host='0.0.0.0',    # Escuchar en todas las interfaces
    port=5001,         # Puerto específico
    debug=True
)
```

### **Paso 2: Obtener IP de la Red**

```bash
# Obtener tu IP local
ipconfig

# Ejemplo de salida:
# Dirección IPv4: 192.168.1.100
```

### **Paso 3: Configurar la App**

En `src/environments/environment.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://192.168.1.100:5001/api',    # Tu IP aquí
  serverUrl: 'http://192.168.1.100:5001'
};
```

### **Paso 4: Configurar Dispositivos**

#### **En la App Móvil:**
- Tab **Configuración** → Cambiar URL → **Guardar**

#### **Para otros dispositivos:**
- Navegador: `http://192.168.1.100:5001`
- API directa: `http://192.168.1.100:5001/api/health`

### **Paso 5: Verificar Conectividad**

```bash
# Desde cualquier dispositivo en la red
curl http://192.168.1.100:5001/api/health

# Respuesta esperada:
# {"success": true, "message": "Servidor i-Tec funcionando correctamente"}
```

## 🧪 Pruebas del Sistema

### **✅ Test 1: Conectividad Básica**

```bash
# Desde terminal
curl http://tu-ip:5001/api/health

# Desde navegador
http://tu-ip:5001/api/health

# Resultado esperado: JSON con success: true
```

### **✅ Test 2: Envío de Datos NFC**

```bash
# Simular lectura NFC
curl -X POST http://tu-ip:5001/api/scan/nfc \
  -H "Content-Type: application/json" \
  -d '{"type":"nfc","content":"Test NFC","nfcType":"NDEF","deviceInfo":{"platform":"test"}}'

# Verificar en dashboard: http://tu-ip:5001
```

### **✅ Test 3: App Móvil**

1. **Conectividad**: Tab Configuración → Test Connection
2. **NFC Simulation**: Tab Scanner → Start NFC Scan  
3. **Datos en vivo**: Ver dashboard web simultáneamente

### **✅ Test 4: Múltiples Dispositivos**

1. **Dispositivo 1**: App móvil escaneando
2. **Dispositivo 2**: Dashboard web abierto
3. **Verificar**: Los escaneos aparecen **inmediatamente** en el dashboard

## 📊 API Reference

### **Endpoints Principales**

| Endpoint | Método | Descripción |
|----------|---------|-------------|
| `/api/health` | GET | Health check del servidor |
| `/api/scan/nfc` | POST | Recibir datos NFC |
| `/api/scan/qr` | POST | Recibir códigos QR |
| `/api/scan/barcode` | POST | Recibir códigos de barras |
| `/api/readings` | GET | Obtener historial de lecturas |
| `/api/stats` | GET | Estadísticas del sistema |

### **Formato de Datos NFC**

```json
{
  "type": "nfc",
  "content": "Contenido del tag NFC",
  "nfcType": "NDEF",
  "timestamp": "2025-08-26T23:35:00Z",
  "deviceInfo": {
    "platform": "android",
    "userAgent": "I-Tec Mobile Scanner",
    "realNFC": true
  }
}
```

### **Respuesta del Servidor**

```json
{
  "success": true,
  "message": "Escaneo NFC procesado correctamente",
  "data": {
    "reading_id": 123,
    "content": "Contenido del tag",
    "timestamp": "2025-08-26T23:35:00Z"
  }
}
```

## 🔒 Seguridad y Permisos

### **Permisos Android Requeridos**
- `android.permission.INTERNET` - Conexión de red
- `android.permission.NFC` - Acceso al hardware NFC
- `android.permission.CAMERA` - Scanner QR/Barcode

### **Configuración de Red**
- **Cleartext Traffic**: Habilitado para conexiones HTTP locales
- **Network Security Config**: Configurado para IPs locales específicas
- **CORS**: Habilitado para conexiones cross-origin

### **Recomendaciones de Producción**
- 🔒 Usar HTTPS en lugar de HTTP
- 🔐 Implementar autenticación de usuarios
- 🛡️ Configurar firewall restrictivo
- 📝 Logs de auditoría

## 🐛 Troubleshooting

### **❌ "Connection Failed" en la App**

**Posibles causas:**
1. IP incorrecta en la configuración
2. Servidor no está ejecutándose
3. Firewall bloqueando el puerto

**Soluciones:**
```bash
# 1. Verificar que el servidor esté activo
curl http://tu-ip:5001/api/health

# 2. Verificar firewall
netsh advfirewall firewall show rule name="I-Tec NFC Server"

# 3. Probar desde navegador del teléfono
# http://tu-ip:5001/api/health
```

### **❌ NFC no Funciona**

**Verificaciones:**
1. ✅ NFC habilitado en configuración del teléfono
2. ✅ App tiene permisos NFC
3. ✅ Tag NFC es compatible (NDEF)
4. ✅ Dispositivo soporta NFC

**Test:**
```bash
# Verificar que el dispositivo detecta NFC
adb shell dumpsys nfc
```

### **❌ App no Compila**

**Problemas comunes:**
```bash
# Error de versión Node.js
node --version  # Debe ser >= 20.19

# Error de dependencias
npm install --legacy-peer-deps --force

# Error de Gradle/Java
# Verificar JAVA_HOME apunta a JDK 17
```

### **❌ Dashboard no Actualiza**

**Verificar WebSockets:**
1. Abrir DevTools del navegador
2. Tab Network → Filter WS
3. Debe aparecer conexión WebSocket activa

## 📈 Monitoreo y Estadísticas

### **Métricas Disponibles**
- 📊 **Total de lecturas** procesadas
- 📱 **Dispositivos únicos** conectados  
- 🕐 **Última actividad** registrada
- 📈 **Lecturas por tipo** (NFC, QR, Barcode)

### **Logs del Sistema**
```bash
# Ver logs en tiempo real del servidor Flask
tail -f I-Tec/nfc_readings.db

# Logs de la app móvil
adb logcat | grep -i "i-tec\|nfc\|scanner"
```

## 🤝 Contribución

Este proyecto está listo para uso en producción y desarrollo. Para contribuir:

1. 🍴 Fork del repositorio
2. 🌿 Crear branch feature
3. ✅ Realizar pruebas completas  
4. 📤 Submit pull request

## 📄 Licencia

Sistema desarrollado para gestión de activos con tecnología NFC. 

---

## 🆘 Soporte

Si tienes problemas:

1. **Revisa esta documentación** completamente
2. **Verifica la conectividad** de red
3. **Consulta los logs** del servidor y app
4. **Usa las herramientas de debug** incluidas

**URLs de prueba rápida:**
- Health Check: `http://tu-ip:5001/api/health`
- Panel Web: `http://tu-ip:5001`
- Móvil Web: `http://tu-ip:5001/mobile`

---

### 🎉 **¡Sistema I-Tec NFC completamente funcional y documentado!** 

**Desarrollado con:** Python Flask, Ionic/Angular, Capacitor, SQLite, WebSockets
