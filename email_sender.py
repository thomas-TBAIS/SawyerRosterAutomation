import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def send_billing_email(sender_email, sender_password, smtp_server, smtp_port, recipient_email, subject, body, attachment_path=None):
    """
    Sends the generated Excel report (or a test email) via SMTP.
    """
    if not sender_email or not sender_password or not recipient_email:
        raise ValueError("Sender email, password, and recipient email must be configured.")
        
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    if attachment_path and os.path.exists(attachment_path):
        filename = os.path.basename(attachment_path)
        try:
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {filename}",
                )
                msg.attach(part)
        except Exception as e:
            raise Exception(f"Failed to attach file: {e}")
            
    try:
        # Establish a secure session
        server = smtplib.SMTP(smtp_server.strip(), int(smtp_port))
        server.starttls()
        server.login(sender_email.strip(), sender_password.strip())
        
        # Send mail
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email.strip(), text)
        server.quit()
        return True
    except Exception as e:
        raise Exception(f"SMTP error: {e}")
