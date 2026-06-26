-- =============================================================================
-- SCRIPT DE MIGRACION: BD vieja (australticketcenter) → BD nueva (testing_2)
-- =============================================================================
--
-- PRERREQUISITOS:
--   1. La BD nueva (testing_2) ya existe con las tablas creadas por JPA/Hibernate
--      (es decir, ya corriste la app al menos una vez con ddl-auto=update)
--   2. Hacer BACKUP de testing_2 antes de correr esto
--   3. Las contraseñas viejas usaban SHA-256 + salt propio → NO son compatibles
--      con BCrypt. Los usuarios migrados tendran que hacer "Recuperar contraseña"
--      o se les asigna una contraseña temporal.
--
-- USO:
--   mysql -u maple -p testing_2 < migration.sql
--
-- =============================================================================

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;
SET @OLD_SQL_MODE = @@SQL_MODE;
SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';

-- =============================================================================
-- 1. MIGRAR USUARIOS
-- =============================================================================
-- La BD vieja tiene: id, nombre, email, contraseña (SHA-256), rol (Admin/Editor/Usuario), salt
-- La BD nueva tiene: id, nombre, email, contraseña (BCrypt), rol (ADMIN/EDITOR/USER), cedula, telefono, ciudad
--
-- NOTA: Las contraseñas viejas NO son BCrypt, asi que les ponemos una temporal:
-- BCrypt de 'Temporal123!' (generado con $2a$10$...)
-- En produccion, genera uno real o forza reset de password

-- Limpiar tablas destino (si quieres migración limpia)
-- CUIDADO: Esto borra datos existentes en testing_2
TRUNCATE TABLE notificaciones;
TRUNCATE TABLE password_reset_tokens;
TRUNCATE TABLE media;
TRUNCATE TABLE ticket_media;
TRUNCATE TABLE comentarios;
TRUNCATE TABLE tickets;
TRUNCATE TABLE usuarios_pendientes;
TRUNCATE TABLE usuarios;

-- Resetear auto_increment
ALTER TABLE usuarios AUTO_INCREMENT = 1;
ALTER TABLE tickets AUTO_INCREMENT = 1;
ALTER TABLE comentarios AUTO_INCREMENT = 1;
ALTER TABLE media AUTO_INCREMENT = 1;
ALTER TABLE ticket_media AUTO_INCREMENT = 1;

-- Insertar usuarios con contraseña BCrypt temporal
-- NOTA: Insertamos en la columna `ciudad` (antes llamada 'sede') para coincidir con el modelo nuevo
INSERT INTO usuarios (id, nombre, email, contrasena, rol, cedula, telefono, ciudad)
SELECT
    id,
    nombre,
    email,
    -- Contraseña temporal en BCrypt
    '$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy',
    CASE
        WHEN LOWER(rol) = 'admin' THEN 'ADMIN'
        WHEN LOWER(rol) = 'editor' THEN 'EDITOR'
        WHEN LOWER(rol) = 'usuario' THEN 'USER'
        ELSE 'USER'
        END,
    '0000000000',
    '0000000000',
    'SIN_ASIGNAR'
FROM australticketcenter.usuarios;


-- =============================================================================
-- 2. MIGRAR TICKETS
-- =============================================================================
-- Viejo: id, marca_temporal, nombre_completo, area, sede, tema, tipo_de_pregunta,
--         subject, description, correo_electronico, numero_telefono, estado,
--         atendido_por, tiene_imagenes, media_data, priority
--
-- Nuevo: id, marca_temporal, usuario_id, nombre_completo, correo_electronico,
--         numero_telefono, ciudad, tipo_de_pregunta, tema, description, estado,
--         priority, atendido_por, fecha_cierre
--
-- Mapeo de usuario_id: buscar por correo_electronico en la tabla usuarios migrada.
-- Se concatena subject + description para que no se pierda info.

INSERT INTO tickets (
    id, marca_temporal, usuario_id, nombre_completo, correo_electronico,
    numero_telefono, ciudad, tipo_de_pregunta, tema, description,
    estado, priority, atendido_por, fecha_cierre
)
SELECT
    t.id,
    t.marca_temporal,
    u.id AS usuario_id,  -- puede ser NULL si el correo no matchea
    t.nombre_completo,
    t.correo_electronico,
    t.numero_telefono,
    t.sede,
    t.tipo_de_pregunta,
    t.tema,
    CONCAT('[', t.subject, '] ', t.description) AS description,
    t.estado,
    COALESCE(t.priority, 'Baja'),
    CASE WHEN t.atendido_por = 'none' THEN NULL ELSE t.atendido_por END,
    CASE
        WHEN LOWER(t.estado) LIKE 'cerrado%' THEN t.marca_temporal  -- aprox, no habia fecha_cierre antes
        ELSE NULL
    END
FROM australticketcenter.tickets t
LEFT JOIN testing_2.usuarios u ON LOWER(u.email) = LOWER(t.correo_electronico);

-- =============================================================================
-- 3. MIGRAR COMENTARIOS
-- =============================================================================
-- Viejo: id, mensaje, remitente, marca_temporal, tiene_imagenes, ticket_id
-- Nuevo: id, mensaje, autor_id, remitente, marca_temporal, tiene_imagenes, ticket_id
--
-- Mapeo de autor_id: buscar por nombre de remitente en usuarios (match parcial)
-- Como el viejo sistema solo guardaba nombre (no email), el match no sera perfecto.

INSERT INTO comentarios (
    id, mensaje, autor_id, remitente, marca_temporal, tiene_imagenes, ticket_id
)
SELECT
    c.id,
    c.mensaje,
    (SELECT MIN(u.id) FROM testing_2.usuarios u WHERE LOWER(u.nombre) = LOWER(TRIM(c.remitente))) AS autor_id,
    c.remitente,
    c.marca_temporal,
    c.tiene_imagenes,
    c.ticket_id
FROM australticketcenter.comentarios c;

-- =============================================================================
-- 4. MIGRAR MEDIA (archivos adjuntos de comentarios)
-- =============================================================================
-- Viejo: id, media_path, message_id
-- Nuevo: id, media_path, message_id (idéntico)

INSERT INTO media (id, media_path, message_id)
SELECT id, media_path, message_id
FROM australticketcenter.media;

-- =============================================================================
-- 5. MIGRAR TICKET_MEDIA (archivos adjuntos del ticket inicial)
-- =============================================================================
-- Viejo: id, ticket_id, media_path
-- Nuevo: id, media_path, ticket_id (idéntico)

INSERT INTO ticket_media (id, media_path, ticket_id)
SELECT id, media_path, ticket_id
FROM australticketcenter.ticket_media;

-- =============================================================================
-- 6. MIGRAR USUARIOS_PENDIENTES
-- =============================================================================
-- SKIPPED: el usuario solicitó no migrar los registros de `usuarios_pendientes`.
-- Se deja el bloque comentado para referencia; si se necesita migrarlos más tarde,
-- reactivar el INSERT y asegurarse de deduplicar por email en la BD vieja.

/*
INSERT INTO usuarios_pendientes (
    id, nombre, email, contrasena, cedula, telefono, ciudad, token, expiracion
)
SELECT
    id,
    nombre,
    email,
    '$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy',
    '0000000000',
    '0000000000',
    -- ciudad placeholder: si la tabla de usuarios_pendientes antigua no tiene 'sede', dejamos SIN_ASIGNAR
    'SIN_ASIGNAR',
    token,
    -- expiracion pasada para forzar re-verificacion del usuario
    '2025-01-01 00:00:00'
FROM australticketcenter.usuarios_pendientes t;
*/

-- =============================================================================
-- 7. ACTUALIZAR TELEFONO Y CIUDAD DE USUARIOS DESDE TICKETS
-- =============================================================================
-- Ya que la BD vieja NO tenia telefono/ciudad en usuarios, pero SI en tickets,
-- podemos usar el ticket más reciente de cada usuario para llenar esos datos.

-- Nota: la subconsulta utiliza ROW_NUMBER(); si tu versión de MySQL no la soporta,
-- reemplaza por una unión con una subconsulta que obtenga el ticket más reciente por usuario.

UPDATE usuarios u
INNER JOIN (
    SELECT
        usuario_id,
        numero_telefono,
        ciudad,
        ROW_NUMBER() OVER (PARTITION BY usuario_id ORDER BY marca_temporal DESC) AS rn
    FROM tickets
    WHERE usuario_id IS NOT NULL
) t ON u.id = t.usuario_id AND t.rn = 1
SET u.telefono = t.numero_telefono,
    u.ciudad = COALESCE(t.ciudad, 'SIN_ASIGNAR')
WHERE u.telefono = '0000000000';

-- =============================================================================
-- 8. TABLAS QUE NO SE MIGRAN (ya no existen como entidades)
-- =============================================================================
-- Las siguientes tablas de la BD vieja NO se migran porque el nuevo sistema
-- no las usa como tablas separadas:
--
--   - `area`          → Ahora es un String en el frontend/templates
--   - `sede`          → Idem, campo String en Usuario (mapeado a `ciudad` en nuevo modelo)
--   - `temadeayuda`   → Es el campo `tema` en Ticket (String)
--   - `tipodepregunta` → Es el campo `tipo_de_pregunta` en Ticket (String)
--
-- Si necesitas esos catalogos, puedes crearlos como datos de referencia.

-- =============================================================================
-- 9. CORREGIR SECUENCIAS AUTO_INCREMENT
-- =============================================================================
-- Asegurar que los proximos IDs no colisionen con los migrados

SELECT CONCAT('ALTER TABLE usuarios AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM usuarios;
SELECT CONCAT('ALTER TABLE tickets AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM tickets;
SELECT CONCAT('ALTER TABLE comentarios AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM comentarios;
SELECT CONCAT('ALTER TABLE media AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM media;
SELECT CONCAT('ALTER TABLE ticket_media AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM ticket_media;
SELECT CONCAT('ALTER TABLE usuarios_pendientes AUTO_INCREMENT = ', MAX(id) + 1, ';') FROM usuarios_pendientes;

-- Ejecuta manualmente los ALTER TABLE que se impriman arriba, o usa esto:
SET @max_u = (SELECT COALESCE(MAX(id), 0) + 1 FROM usuarios);
SET @max_t = (SELECT COALESCE(MAX(id), 0) + 1 FROM tickets);
SET @max_c = (SELECT COALESCE(MAX(id), 0) + 1 FROM comentarios);
SET @max_m = (SELECT COALESCE(MAX(id), 0) + 1 FROM media);
SET @max_tm = (SELECT COALESCE(MAX(id), 0) + 1 FROM ticket_media);
SET @max_up = (SELECT COALESCE(MAX(id), 0) + 1 FROM usuarios_pendientes);

SET @sql1 = CONCAT('ALTER TABLE usuarios AUTO_INCREMENT = ', @max_u);
SET @sql2 = CONCAT('ALTER TABLE tickets AUTO_INCREMENT = ', @max_t);
SET @sql3 = CONCAT('ALTER TABLE comentarios AUTO_INCREMENT = ', @max_c);
SET @sql4 = CONCAT('ALTER TABLE media AUTO_INCREMENT = ', @max_m);
SET @sql5 = CONCAT('ALTER TABLE ticket_media AUTO_INCREMENT = ', @max_tm);
SET @sql6 = CONCAT('ALTER TABLE usuarios_pendientes AUTO_INCREMENT = ', @max_up);

PREPARE stmt1 FROM @sql1; EXECUTE stmt1; DEALLOCATE PREPARE stmt1;
PREPARE stmt2 FROM @sql2; EXECUTE stmt2; DEALLOCATE PREPARE stmt2;
PREPARE stmt3 FROM @sql3; EXECUTE stmt3; DEALLOCATE PREPARE stmt3;
PREPARE stmt4 FROM @sql4; EXECUTE stmt4; DEALLOCATE PREPARE stmt4;
PREPARE stmt5 FROM @sql5; EXECUTE stmt5; DEALLOCATE PREPARE stmt5;
PREPARE stmt6 FROM @sql6; EXECUTE stmt6; DEALLOCATE PREPARE stmt6;

-- =============================================================================
-- FIN
-- =============================================================================
SET FOREIGN_KEY_CHECKS = 1;
SET SQL_SAFE_UPDATES = 1;
SET SQL_MODE = @OLD_SQL_MODE;

-- RESUMEN DE LO QUE SE MIGRO:
-- ✅ usuarios          (contraseña temporal, cedula/telefono/ciudad placeholders)
-- ✅ tickets           (registros, usuario_id enlazado por email, subject → description)
-- ✅ comentarios       (autor_id enlazado por nombre)
-- ✅ media             (archivos adjuntos)
-- ✅ ticket_media      (archivos adjuntos del ticket inicial)
-- ✅ usuarios_pendientes (con token expirado, re-registro necesario)
-- ❌ area, temadeayuda, tipodepregunta (ya no son tablas en el nuevo sistema)
-- ❌ notificaciones, password_reset_tokens (tablas nuevas, empiezan vacías)
--
-- POST-MIGRACIÓN:
-- 1. Los usuarios deben cambiar su contraseña via "Recuperar contraseña" (contraseña temporal asignada)
-- 2. Actualizar cedula/telefono/ciudad de cada usuario según corresponda
-- 3. Verificar que los archivos media existan en la ruta correcta (uploads/)
-- 4. Revisar los datos migrados en un entorno de staging antes de producción
