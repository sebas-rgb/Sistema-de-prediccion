package com.maple.back.services.auth;

import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

@Service
public class ValidationService {

    private static final Pattern NOMBRE_PATTERN =
        Pattern.compile("^[\\p{L} ]{3,110}$");

    private static final Pattern EMAIL_PATTERN =
        Pattern.compile("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");

    private static final Pattern CEDULA_PATTERN =
        Pattern.compile("^\\d{6,12}$");

    private static final Pattern TELEFONO_PATTERN =
        Pattern.compile("^\\d{1,15}$");

    public static final Set<String> CIUDADES_VALIDAS = Set.of(
        "BARRANQUILLA","BOGOTA","BUCARAMANGA","CALI","CHIA","CUCUTA",
        "MANIZALES","MEDELLIN","NEIVA","PEREIRA","RIONEGRO","SOACHA","TUNJA",
        "ARMENIA","IBAGUE","MONTERIA","SINCELEJO","TULUA","VILLAVICENCIO","YOPAL","SANTA MARTA","CARTAGENA", "PASTO"
    );

    public static final Set<String> PUNTOS_VALIDOS = Set.of(
        "DISTRIBUIDORES","ADMINISTRATIVO", "ARCHIVO", "BARRANQUILLA", "BODEGA", "BUCARAMANGA",
        "CALI", "CENTRO", "CHAPINERO", "CHIA", "CUCUTA", "LABORATORIO",
        "MANIZALES", "MEDELLIN", "NEIVA", "OLAYA", "PEREIRA",
        "PRINCIPAL", "RIONEGRO", "TUNJA", "CARTAGENA", "PASTO"
    );

    public static final Set<String> CARGOS_VALIDOS = Set.of(
        "NO APLICA",
        "ADMINISTRADOR/A",
        "ANALISTA DE CARTERA",
        "ASESOR JURIDICO",
        "ASISTENTE DE AUDITORIA",
        "ASISTENTE DE CONTABILIDAD",
        "ASISTENTE DE GERENCIA",
        "ASISTENTE DE NOMINA",
        "ASISTENTE DE TALENTO HUMANO",
        "AUDITOR INTERNO",
        "AUXILIAR DE ARCHIVO",
        "AUXILIAR DE BODEGA",
        "AUXILIAR DE IMAGEN CORPORATIVA",
        "AUXILIAR DE LABORATORIO",
        "AUXILIAR DE LABORATORIO - ANTIRREFLEJO",
        "AUXILIAR DE LABORATORIO - CALL CENTER",
        "AUXILIAR DE LABORATORIO - CONTROL DE CALIDAD",
        "AUXILIAR DE LABORATORIO - ENCINTADO",
        "AUXILIAR DE LABORATORIO - TALLA",
        "AUXILIAR DE PUNTO DE VENTA",
        "AUXILIAR DE SERVICIOS GENERALES",
        "AUXILIAR DE SERVICIOS VARIOS",
        "BISELADOR/A",
        "CAJERO",
        "COORDINADOR DE ARCHIVO Y SUMINISTROS",
        "COORDINADOR DE BISEL",
        "COORDINADOR DE BODEGA",
        "COORDINADOR DE LABORATORIO",
        "COORDINADORA CONTABLE",
        "DIRECTOR CIENTIFICO",
        "DIRECTOR COMERCIAL",
        "DIRECTORA CONTABLE Y TESORERIA",
        "DIRECTORA DE GESTION DE MARCA",
        "DIRECTORA DE HSEQ",
        "DIRECTORA DE IMAGEN COORPORATIVA",
        "DIRECTORA DE TALENTO HUMANO",
        "EJECUTIVO COMERCIAL",
        "GERENTE ADMINISTRATIVO Y FINANCIERO",
        "GERENTE COMERCIAL",
        "JEFE DE BODEGA",
        "JEFE DE LABORATORIO",
        "LIDER DE SISTEMAS",
        "MENSAJERO",
        "PRESIDENTE",
        "APRENDIZ"
    );

    /**
     * Valida los campos de registro
     */
    public List<String> validarRegistro(String nombre, String email, String password,
                                        String confirmPassword, String cedula,
                                        String telefono, String ciudad,
                                        String punto, String cargo) {
        List<String> errores = new ArrayList<>();

        // Validar campos vacíos
        if (nombre == null || nombre.trim().isEmpty()) {
            errores.add("El nombre es obligatorio");
        } else if (!NOMBRE_PATTERN.matcher(nombre.trim()).matches()) {
            errores.add("El nombre debe tener entre 3 y 110 letras");
        }

        if (email == null || email.trim().isEmpty()) {
            errores.add("El email es obligatorio");
        } else if (!EMAIL_PATTERN.matcher(email).matches()) {
            errores.add("El formato del email no es válido");
        }

        if (password == null || password.isEmpty()) {
            errores.add("La contraseña es obligatoria");
        } else if (password.length() < 6) {
            errores.add("La contraseña debe tener al menos 6 caracteres");
        }

        if (confirmPassword == null || confirmPassword.isEmpty()) {
            errores.add("Debe confirmar la contraseña");
        } else if (password != null && !password.equals(confirmPassword)) {
            errores.add("Las contraseñas no coinciden");
        }

        if (cedula == null || cedula.trim().isEmpty()) {
            errores.add("La cédula es obligatoria");
        } else if (!CEDULA_PATTERN.matcher(cedula).matches()) {
            errores.add("La cédula debe contener entre 6 y 12 dígitos");
        }

        if (telefono == null || telefono.trim().isEmpty()) {
            errores.add("El teléfono es obligatorio");
        } else if (!TELEFONO_PATTERN.matcher(telefono).matches()) {
            errores.add("El teléfono debe contener entre 1 y 15 dígitos");
        }

        if (ciudad == null || ciudad.trim().isEmpty()) {
            errores.add("La ciudad es obligatoria");
        } else if (!CIUDADES_VALIDAS.contains(ciudad.trim().toUpperCase())) {
            errores.add("La ciudad seleccionada no es válida");
        }

        if (punto == null || punto.trim().isEmpty()) {
            errores.add("El punto es obligatorio");
        } else if (!PUNTOS_VALIDOS.contains(punto.trim().toUpperCase())) {
            errores.add("El punto seleccionado no es válido");
        }

        if (cargo == null || cargo.trim().isEmpty()) {
            errores.add("El cargo es obligatorio");
        } else if (!CARGOS_VALIDOS.contains(cargo.trim().toUpperCase())) {
            errores.add("El cargo seleccionado no es válido");
        }

        return errores;
    }

    /**
     * Valida el formato de email
     */
    public boolean esEmailValido(String email) {
        return email != null && EMAIL_PATTERN.matcher(email).matches();
    }

    /**
     * Valida el formato de cédula
     */
    public boolean esCedulaValida(String cedula) {
        return cedula != null && CEDULA_PATTERN.matcher(cedula).matches();
    }

    /**
     * Valida el formato de teléfono
     */
    public boolean esTelefonoValido(String telefono) {
        return telefono != null && TELEFONO_PATTERN.matcher(telefono).matches();
    }
}
