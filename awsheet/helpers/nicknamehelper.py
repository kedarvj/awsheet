from .awshelper import AWSHelper
import boto
import re
import time

DNS_SLEEP_TIME = 5.0

class NickNameHelper(AWSHelper):
    """modular and convergent route53 "nickname" records (CNAME for public ip. A for private ip)"""

    def __init__(self, heet, name, value, **kwargs):
        self.heet = heet
        self.name = name
        self.value = value
        self.zone_id = self.heet.get_value('zone_id', required=True)
        self.domain = self.heet.get_value('domain', required=True)
        self.ttl = self.heet.get_value('ttl', kwargs, default=60)

        self.conn = self.heet.get_aws_service_connection(service_name='route53')

        #self.conn = boto.connect_route53(
        #    aws_access_key_id=heet.access_key_id,
        #    aws_secret_access_key=heet.secret_access_key)

        # get_zone does not like leading periods
        self.zone = self.conn.get_zone(self.domain.lstrip('.'))
        heet.add_resource(self)

    def __str__(self):
        return "NickName %s" % self.name

    def get_resource_object(self):
        """return boto object for DNS record. Might be of type A or CNAME"""
        rec = self.zone.find_records(self.name, 'A')
        if rec:
            return rec
        rec = self.zone.find_records(self.name, 'CNAME')
        return rec

    def converge(self):
        # if the target is a subclass of AWSHelper, execute the overloaded method to get the true target
        if isinstance(self.value, AWSHelper):
            cname_target = self.value.get_cname_target()
            #- may return None, in which case, we are done
            if not cname_target:
                return None
            else:
                self.value = cname_target

        current_record = self.get_resource_object()

        if current_record and current_record.resource_records:
            current_value = current_record.resource_records[0]
            # if record already exists AND points at correct value, do nothing
            if current_value == self.value:
                return self
            # if record already exists AND points at wrong value, delete it before creating new record
            self.heet.logger.info("deleting old record %s to %s" % (self.name, current_value))
            time.sleep(DNS_SLEEP_TIME)
            self.zone.delete_record(current_record)

        # If the target is an IP address, we must create an A
        # record. If the target is a DNS name, we want a CNAME
        self.type = 'A' if re.match('^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', self.value) else 'CNAME'

        self.heet.logger.info("creating %s record %s to %s for ttl=%s" % (self.type, self.name, self.value, self.ttl))
        changes = boto.route53.record.ResourceRecordSets(self.conn, self.zone_id)
        change = changes.add_change("CREATE", self.name, self.type, self.ttl)
        change.add_value(self.value)
        time.sleep(DNS_SLEEP_TIME)
        result = changes.commit()
        return self

    def destroy(self):
        current_record = self.get_resource_object()
        if not current_record:
            return
        self.heet.logger.info("deleting record %s %s" % (self.name, current_record))
        time.sleep(DNS_SLEEP_TIME)
        self.zone.delete_record(current_record)
