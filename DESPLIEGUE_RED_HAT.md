# Despliegue CRT Planificador Web en Red Hat · puerto 8086

**Uso previsto:** laboratorio o red interna aislada. Esta versión **NO tiene autenticación, control de acceso por usuario ni HTTPS**. Cualquier equipo con acceso al puerto puede listar, crear, modificar y borrar tareas. No exponer a Internet ni usar datos sensibles en esta etapa.

## Requisitos

- RHEL 9.2+ (o una distribución Red Hat con `python3.11` disponible), acceso `sudo`.
- `firewalld` habilitado si gestiona el cortafuegos. Verificar con `sudo firewall-cmd --state`.
- Archivo ZIP `CRT_Planificador_RedHat_8086.zip` en el servidor.
- Ajustar la red IP autorizada en el paso del firewall.

## Instalación

Copiar el ZIP al servidor, entrar mediante SSH y ejecutar:

```bash
sudo dnf install -y python3.11 unzip
python3.11 --version
sudo useradd --system --home-dir /opt/crt-planificador --shell /sbin/nologin crtapp
sudo unzip -q CRT_Planificador_RedHat_8086.zip -d /opt/
sudo mkdir -p /opt/crt-planificador/datos
sudo chown -R root:root /opt/crt-planificador
sudo chown -R crtapp:crtapp /opt/crt-planificador/datos
sudo chmod 750 /opt/crt-planificador/datos
sudo cp /opt/crt-planificador/deploy/crt-planificador.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crt-planificador
sudo systemctl status crt-planificador --no-pager
curl -fsS http://127.0.0.1:8086/api/info
```

Si el usuario `crtapp` ya existe, no vuelvas a crearlo; continúa a partir del `unzip`. El directorio `/opt/crt-planificador/datos` contiene la base de datos SQLite; haz respaldos antes de sobrescribir instalaciones previas. Si se instala sobre una versión existente, **no reemplaces ni borres `datos`**.

## Firewall: SOLO red interna

Detectar zona activa con `sudo firewall-cmd --get-active-zones`. Sustituye `192.168.1.0/24` por la subred autorizada real y `public` por la zona real:

```bash
sudo firewall-cmd --permanent --zone=public --add-rich-rule='rule family="ipv4" source address="192.168.1.0/24" port port="8086" protocol="tcp" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --zone=public --list-rich-rules
```

No uses `--add-port=8086/tcp` abierto a todo el mundo. Verifica que ninguna otra regla ya permita el puerto ampliamente; otros cortafuegos o ACL de red también pueden aplicar.

URL remota desde un equipo autorizado: `http://IP_DEL_SERVIDOR:8086/`.

## Operación

```bash
sudo systemctl restart crt-planificador
sudo systemctl stop crt-planificador
sudo journalctl -u crt-planificador -n 80 --no-pager
sudo ss -lntp | grep ':8086'
sudo -u crtapp python3.11 -m unittest discover -s /opt/crt-planificador/tests -v
```

Se crea la base de datos en `/opt/crt-planificador/datos/crt_planificador.sqlite3` al arrancar. Para respaldo consistente detén brevemente el servicio antes de copiar la base, o usa la API de backup de SQLite con un procedimiento validado. 

## Problemas comunes

- `Connection refused`: revisa servicio, `ss`, dirección IP y archivo `server.py` corregido con `--host`.
- `Permission denied` o `database is locked`: revisar permisos del directorio `datos` y diagnósticos de SELinux (`sudo ausearch -m AVC -ts recent`). No deshabilites SELinux para solucionar un problema.
- Puerto ocupado: `sudo ss -lntp | grep ':8086'`.
- RHEL con Python menor que 3.10: instala una versión 3.10+ compatible o edita `ExecStart` para señalarla.

## Producción

Antes de usar para tareas institucionales reales: poner detrás de proxy HTTPS, integrar autenticación institucional y autorización por usuario, añadir copias de seguridad y revisar la seguridad del API. Una instalación de `systemd` **no convierte el prototipo en producción segura**.
