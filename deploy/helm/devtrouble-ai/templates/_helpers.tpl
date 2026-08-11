{{/* 차트/릴리스 이름 조합. release name이 이미 chart name을 포함하면 중복 안 붙인다. */}}
{{- define "devtrouble-ai.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/* 공통 라벨. 반드시 root context(.)로 호출할 것 — dict를 넘기면 안 됨. */}}
{{- define "devtrouble-ai.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "devtrouble-ai.selectorLabels" . }}
{{- end }}

{{/* 공통 셀렉터 라벨. 반드시 root context(.)로 호출할 것. */}}
{{- define "devtrouble-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* 컴포넌트별 라벨. 호출 시 (dict "root" $ "component" "api") 형태로 넘길 것. */}}
{{- define "devtrouble-ai.componentLabels" -}}
{{ include "devtrouble-ai.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* 컴포넌트별 셀렉터 라벨. 호출 시 (dict "root" $ "component" "api") 형태로 넘길 것. */}}
{{- define "devtrouble-ai.componentSelectorLabels" -}}
{{ include "devtrouble-ai.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* ServiceAccount 이름 */}}
{{- define "devtrouble-ai.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "devtrouble-ai.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/* 이미지 참조 조립. 호출 시 (dict "root" $ "repository" .Values.image.backend.repository "tag" .Values.image.backend.tag) 형태로 넘길 것. */}}
{{- define "devtrouble-ai.image" -}}
{{- $registry := .root.Values.image.registry -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry .repository .tag -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end }}
