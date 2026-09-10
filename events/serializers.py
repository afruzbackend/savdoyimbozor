from rest_framework import serializers

from .models import CameraTamperEvent, CustomerVisit, SaleObservation


class EventIngestSerializer(serializers.Serializer):
    """AI worker yuboradigan hodisaning umumiy formati.

    type: "visit" | "tamper" | "sale_observation"
    shop_id: qaysi do'kon (visit/sale uchun majburiy)
    timestamp: ISO-8601 vaqt
    payload: turga qarab qo'shimcha maydonlar
    """
    type = serializers.ChoiceField(choices=["visit", "tamper", "sale_observation"])
    shop_id = serializers.IntegerField(required=False)
    timestamp = serializers.DateTimeField()
    payload = serializers.DictField(required=False, default=dict)


class CustomerVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerVisit
        fields = "__all__"


class CameraTamperSerializer(serializers.ModelSerializer):
    class Meta:
        model = CameraTamperEvent
        fields = "__all__"


class SaleObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleObservation
        fields = "__all__"
