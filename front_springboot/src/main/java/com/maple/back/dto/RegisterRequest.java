package com.maple.back.dto;

public class RegisterRequest {
    private String nombre;
    private String email;
    private String password;
    private String confirmPassword;
    private String cedula;
    private String telefono;
    private String ciudad;
    private String punto;
    private String cargo;

    // Constructor
    public RegisterRequest() {}

    public RegisterRequest(String nombre, String email, String password, String confirmPassword,
                          String cedula, String telefono, String ciudad,
                          String punto, String cargo) {
        this.nombre = nombre;
        this.email = email;
        this.password = password;
        this.confirmPassword = confirmPassword;
        this.cedula = cedula;
        this.telefono = telefono;
        this.ciudad = ciudad;
        this.punto = punto;
        this.cargo = cargo;
    }

    // Getters y Setters
    public String getNombre() {
        return nombre;
    }

    public void setNombre(String nombre) {
        this.nombre = nombre;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getConfirmPassword() {
        return confirmPassword;
    }

    public void setConfirmPassword(String confirmPassword) {
        this.confirmPassword = confirmPassword;
    }

    public String getCedula() {
        return cedula;
    }

    public void setCedula(String cedula) {
        this.cedula = cedula;
    }

    public String getTelefono() {
        return telefono;
    }

    public void setTelefono(String telefono) {
        this.telefono = telefono;
    }

    public String getCiudad() {
        return ciudad;
    }

    public void setCiudad(String ciudad) {
        this.ciudad = ciudad;
    }

    public String getPunto() {
        return punto;
    }

    public void setPunto(String punto) {
        this.punto = punto;
    }

    public String getCargo() {
        return cargo;
    }

    public void setCargo(String cargo) {
        this.cargo = cargo;
    }
}
