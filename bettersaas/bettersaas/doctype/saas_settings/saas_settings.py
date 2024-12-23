# Copyright (c) 2023, OneHash and contributors
# For license information, please see license.txt

import os
import frappe
import shutil
from datetime import datetime
from frappe import _
from frappe.utils.password import decrypt
from frappe.model.document import Document

def get_days_since_creation(folder_path):
    try:
        creation_time = os.path.getctime(folder_path)
        creation_date = datetime.fromtimestamp(creation_time)
        days_since_creation = (datetime.now() - creation_date).days
        return days_since_creation
    except Exception as e:
        return f"An error occurred: {e}"
    
@frappe.whitelist()
def delete_archived_sites():
    conf = frappe.get_doc('SaaS Settings')
    if not conf.arch_site_delete_conf_enabled:
        return
    directory_path = conf.path
    threshold_days = conf.threshold_days
    try:
        for folder_name in os.listdir(directory_path):
            folder_path = os.path.join(directory_path, folder_name)
            if os.path.isdir(folder_path):
                days_since_creation = get_days_since_creation(folder_path)
                if isinstance(days_since_creation, int) and days_since_creation > threshold_days:
                      shutil.rmtree(folder_path)
    except Exception as e:
        frappe.msgprint(f"An error occurred: {e}")

def send_email(
    email,
    content,
):
    subject = "Account Status"
    template = "account_status_email"
    args = {
        "content": content
    }
    frappe.sendmail(
        recipients=email,
        subject=subject,
        template=template,
        args=args,
        delayed=False,
    )
    return True

def get_last_login_date(site_name):
    from frappe.frappeclient import FrappeClient
    site = frappe.db.get("SaaS Sites", filters={"site_name": site_name})
    site_password = decrypt(site.encrypted_password, frappe.conf.encryption_key)
    conn = FrappeClient("http://"+site_name, "Administrator", site_password)
    active_users_last_active = conn.get_list('User', fields = ['last_active'], filters = {'enabled':'1'},limit_page_length=10000)
    latest_last_active = max(
        (datetime.fromisoformat(user['last_active']) for user in active_users_last_active if user['last_active']),
        default=None
    )
    return latest_last_active
     
@frappe.whitelist()
def delete_free_sites():
    sites = frappe.get_list("SaaS Sites", fields=["site_name"])
    to_be_deleted = []
    for site in sites:
        try:
            site_config = frappe.get_site_config(site_path=site.site_name)
            if site_config["subscription_status"] != "active":
                to_be_deleted.append(site)
        except:
            pass
    for site in to_be_deleted:
        saas_settings = frappe.get_doc("SaaS Settings")
        site_config = frappe.get_site_config(site_path=site.site_name)
        linked_email = site_config.customer_email
        subscription_ends_on = datetime.strptime(site_config.subscription_ends_on, "%Y-%m-%d")

        last_login_date = get_last_login_date(site.site_name)
        present_date = datetime.now()
        inactive_days = (present_date - last_login_date).days
        if inactive_days >= saas_settings.inactive_for_days:
            content = "This is to inform you that your OneHash account with the email address {email_address} has been permanently deleted on {exp_date}. You will no longer be able to access your account or recover any data".format(
				email_address=linked_email, exp_date=subscription_ends_on.strftime("%d-%m-%y")
			)
            send_email(linked_email, content)
            method = "bettersaas.api.delete_site"
            frappe.enqueue(
                method, 
                queue="short", 
                site_name=site.site_name
            )
        elif inactive_days >= saas_settings.inactive_for_days - saas_settings.warning_days:
            content = "This is to inform you that your OneHash account with the email address {email_address} will be permanently deleted on {exp_date}. You will no longer be able to access your account or recover any data".format(
				email_address=linked_email, exp_date=subscription_ends_on.strftime("%d-%m-%y")
			)
            send_email(linked_email, content)
        elif inactive_days >= saas_settings.inactive_for_days - saas_settings.intermittent_warning_days:
            content = "This is to inform you that your OneHash account with the email address {email_address} will be permanently deleted on {exp_date}. You will no longer be able to access your account or recover any data".format(
				email_address=linked_email, exp_date=subscription_ends_on.strftime("%d-%m-%y")
		  	)
            send_email(linked_email, content)
    return "success"

class SaaSSettings(Document):
	pass
