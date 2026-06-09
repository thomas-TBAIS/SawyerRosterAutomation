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

def send_sms_notification(sender_email, sender_password, smtp_server, smtp_port, phone_numbers, body):
    """
    Sends a text message notification via T-Mobile email-to-SMS gateway (tmomail.net).
    """
    if not sender_email or not sender_password or not phone_numbers:
        return False
        
    import re
    # Clean and parse phone numbers
    recipients = []
    for num in phone_numbers.split(','):
        num = num.strip()
        if not num:
            continue
        # If it already looks like an email address, keep it
        if '@' in num:
            recipients.append(num)
        else:
            # Clean non-digits and check if it has 10 digits
            clean_num = re.sub(r'\D', '', num)
            if len(clean_num) == 10:
                recipients.append(f"{clean_num}@tmomail.net")
            elif len(clean_num) == 11 and clean_num.startswith('1'):
                recipients.append(f"{clean_num[1:]}@tmomail.net")
                
    if not recipients:
        return False
        
    try:
        # Establish SMTP connection
        server = smtplib.SMTP(smtp_server.strip(), int(smtp_port))
        server.starttls()
        server.login(sender_email.strip(), sender_password.strip())
        
        for recipient in recipients:
            # Clean body of non-ASCII characters for basic gateway compatibility
            clean_body = body.encode('ascii', 'ignore').decode('ascii')
            # Normalize double quotes to single quotes
            clean_body = clean_body.replace('"', "'")
            
            # Use MIMEMultipart with empty subject (proven to bypass gateway spam filters)
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient
            msg['Subject'] = "" 
            msg.attach(MIMEText(clean_body, 'plain'))
            
            server.sendmail(sender_email, recipient, msg.as_string())
            
        server.quit()
        return True
    except Exception as e:
        raise Exception(f"SMS Gateway SMTP error: {e}")
