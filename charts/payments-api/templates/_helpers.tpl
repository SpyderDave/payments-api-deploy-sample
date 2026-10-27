{{- define "payments-api.image" -}}
{{ .Values.image.repository }}@{{ required "image.digest is required" .Values.image.digest }}
{{- end }}

{{- define "payments-api.selectorLabels" -}}
app.kubernetes.io/name: payments-api
{{- end }}

{{- define "payments-api.batchSelectorLabels" -}}
app.kubernetes.io/name: payments-api-batch
{{- end }}
