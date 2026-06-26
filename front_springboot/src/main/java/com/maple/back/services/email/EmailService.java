package com.maple.back.services.email;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class EmailService {

    private final JavaMailSender mailSender;

    @Value("${app.base-url}")
    private String baseUrl;

    public EmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void enviarRespuestaTicket(String para, String nombre, String mensaje, Integer ticketId) {

        String asunto = "Respuesta a tu Ticket #" + ticketId;

        String contenido = """
                <html>
                  <body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:30px;">
                    <style>
                      @media (max-width: 600px) {
                        body { padding: 15px; }
                        .container { padding: 20px; }
                        h2 { font-size: 22px; }
                        p { font-size: 15px; }
                        blockquote { font-size: 14px; padding-left: 10px; }
                        .footer { padding: 15px; font-size: 12px; }
                      }
                    </style>
                    <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.1); overflow:hidden;" class="container">

                      <div style="background-color:#38bdf8; padding:25px; text-align:center;">
                        <img src="https://www.australlens.com/images/logo-austral.png" alt="Austral Lens" style="max-width:200px;">
                      </div>

                      <div style="padding:35px;">
                        <h2 style="color:#0ea5e9; font-size:26px;">Respuesta a tu Ticket</h2>

                        <p style="font-size:17px;">Hola <strong>%s</strong>,</p>

                        <p style="font-size:17px;">Hemos respondido tu solicitud:</p>

                        <blockquote style="border-left:6px solid #0ea5e9; padding-left:15px; margin:25px 0; font-size:16px; background:#f0f9ff;">
                          %s
                        </blockquote>

                        <p style="font-size:17px;">
                          Saludos cordiales,<br>
                          <strong>Equipo Austral Lens</strong>
                        </p>
                      </div>

                      <div style="background:#e0f2fe; padding:20px; text-align:center; font-size:14px;" class="footer">
                        <p><strong>Austral Lens</strong></p>
                        <p>Cra. 40 #20a-25</p>
                        <p style="font-size:12px;">Ticket #%d</p>
                      </div>

                    </div>
                  </body>
                </html>
                """.formatted(nombre, mensaje, ticketId);

        enviarCorreo(para, asunto, contenido);
    }

    public void enviarRecuperacionPassword(String para, String nombre, String token) {

        String asunto = "Recuperación de contraseña - Centro de Tickets";
        String enlace = baseUrl + "/reset-password?token=" + token;

        String contenido = """
                <html>
                  <body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:30px;">
                    <style>
                      @media (max-width: 600px) {
                        body { padding: 15px; }
                        .container { padding: 20px; }
                        h2 { font-size: 22px; }
                        p { font-size: 15px; }
                        a { padding: 10px 20px; font-size: 14px; }
                        .footer { padding: 15px; font-size: 12px; }
                      }
                    </style>
                    <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.1); overflow:hidden;" class="container">

                      <div style="background-color:#38bdf8; padding:25px; text-align:center;">
                        <h2 style="color:white;">Centro de Soporte TI</h2>
                      </div>

                      <div style="padding:35px;">
                        <h2 style="color:#0ea5e9;">Recuperación de contraseña</h2>

                        <p>Hola <strong>%s</strong>,</p>

                        <p>Recibimos una solicitud para restablecer tu contraseña.</p>

                        <div style="text-align:center; margin:30px 0;">
                          <a href="%s"
                             style="background-color:#0ea5e9; color:white; padding:12px 25px;
                                    text-decoration:none; border-radius:6px;
                                    font-weight:bold;">
                             Restablecer contraseña
                          </a>
                        </div>

                        <p style="font-size:14px; color:#555;">
                          Si no solicitaste este cambio puedes ignorar este correo.
                        </p>

                      </div>

                      <div style="background:#e0f2fe; padding:20px; text-align:center; font-size:12px;" class="footer">
                        Centro de Tickets - Mesa de ayuda interna
                      </div>

                    </div>
                  </body>
                </html>
                """.formatted(nombre, enlace);

        enviarCorreo(para, asunto, contenido);
    }

    public void enviarTicketCerrado(String correo, String nombre, Integer ticketId) {

        String asunto = "Tu ticket ha sido cerrado #" + ticketId;

        String contenido = """
                <html>
                  <body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:30px;">
                    <style>
                      @media (max-width: 600px) {
                        body { padding: 15px; }
                        .container { padding: 20px; text-align: center; }
                        h2 { font-size: 22px; }
                        p { font-size: 15px; }
                        .footer { padding: 15px; font-size: 12px; }
                      }
                    </style>
                    <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.1); overflow:hidden;" class="container">

                      <div style="background-color:#38bdf8; padding:25px; text-align:center;">
                        <img src="https://www.australlens.com/images/logo-austral.png" alt="Austral Lens" style="max-width:200px;">
                      </div>

                      <div style="padding:35px; text-align:center;">
                        <h2 style="color:#0ea5e9;">Ticket Cerrado</h2>

                        <p style="font-size:17px;">Hola <strong>%s</strong>,</p>

                        <p style="font-size:17px;">
                          Tu ticket <strong>#%d</strong> ha sido marcado como
                          <strong style="color:#16a34a;">CERRADO</strong>
                          por el equipo de soporte.
                        </p>

                        <p style="font-size:16px; margin-top:20px;">
                          Si el problema persiste puedes crear un nuevo ticket desde el sistema.
                        </p>

                        <p style="margin-top:30px;">
                          Saludos cordiales,<br>
                          <strong>Equipo Austral Lens</strong>
                        </p>

                      </div>

                      <div style="background:#e0f2fe; padding:20px; text-align:center; font-size:12px;" class="footer">
                        Austral Lens - Sistema de soporte técnico
                      </div>

                    </div>
                  </body>
                </html>
                """.formatted(nombre, ticketId);

        enviarCorreo(correo, asunto, contenido);
    }

    public void enviarVerificacionCuenta(String para, String nombre, String token) {

        String asunto = "Verifica tu cuenta - Austral Lens";
        String link = baseUrl + "/verificar?token=" + token;

        String contenido = """
                <html>
                  <body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:30px;">
                    <style>
                      @media (max-width: 600px) {
                        body { padding: 15px; }
                        .container { padding: 20px; }
                        h2 { font-size: 22px; }
                        p { font-size: 15px; }
                        a { padding: 12px 25px; font-size: 16px; }
                        .footer { padding: 15px; font-size: 12px; }
                      }
                    </style>
                    <div style="max-width:700px; margin:auto; background:#ffffff; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.1); overflow:hidden;" class="container">

                      <div style="background-color:#38bdf8; padding:25px; text-align:center;">
                        <img src="https://www.australlens.com/images/logo-austral.png" alt="Austral Lens" style="max-width:200px;">
                      </div>

                      <div style="padding:35px;">
                        <h2 style="color:#0ea5e9; font-size:26px;">Verifica tu cuenta</h2>

                        <p style="font-size:17px;">Hola <strong>%s</strong>,</p>

                        <p style="font-size:17px;">Gracias por registrarte. Haz click en el siguiente boton para activar tu cuenta:</p>

                        <div style="text-align:center; margin:30px 0;">
                          <a href="%s"
                             style="background-color:#0ea5e9; color:#ffffff; padding:14px 35px; border-radius:8px; text-decoration:none; font-size:18px; font-weight:bold;">
                            Verificar mi cuenta
                          </a>
                        </div>

                        <p style="font-size:14px; color:#888;">
                          Si no creaste esta cuenta, puedes ignorar este correo.<br>
                          Este enlace expira en 24 horas.
                        </p>

                        <p style="font-size:17px;">
                          Saludos cordiales,<br>
                          <strong>Equipo Austral Lens</strong>
                        </p>
                      </div>

                      <div style="background:#e0f2fe; padding:20px; text-align:center; font-size:14px;" class="footer">
                        <p><strong>Austral Lens</strong></p>
                      </div>

                    </div>
                  </body>
                </html>
                """.formatted(nombre, link);

        enviarCorreo(para, asunto, contenido);
    }

    private void enviarCorreo(String correo, String asunto, String contenido) {

        try {

            MimeMessage mimeMessage = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(mimeMessage, true, "UTF-8");

            helper.setTo(correo);
            helper.setSubject(asunto);
            helper.setText(contenido, true);

            mailSender.send(mimeMessage);

        } catch (MessagingException e) {
            throw new RuntimeException("Error al enviar correo", e);
        }
    }
}

