{{/*
차트/릴리스 이름 조합. release name이 이미 chart name을 포함하면 중복 안 붙인다.
*/}}
{{- define "devtrouble-ai.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/* 공통 라벨 */}}
{{- define "devtrouble-ai.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "devtrouble-ai.selectorLabels" . }}
{{- end }}

{{/* 컴포넌트별 셀렉터 라벨. 호출 시 dict "root" $ "component" "api" 형태로 넘긴다. */}}
{{- define "devtrouble-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "devtrouble-ai.componentLabels" -}}
{{ include "devtrouble-ai.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

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

{{/* 이미지 참조 조립 (registry가 있으면 붙이고, 없으면 repository 그대로) */}}
{{- define "devtrouble-ai.image" -}}
{{- $registry := .root.Values.image.registry -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry .repository .tag -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end }}

{{/*
DATABASE_URL 등 인프라 접속 문자열. mysql.enabled/redis.enabled/qdrant.enabled가 true면
클러스터 내부 Service 주소로 자동 조립하고, false면 secrets.*에 직접 넣은 값(RDS/ElastiCache
등 외부 관리형 서비스 주소)을 그대로 쓴다.
*/}}
{{- define "devtrouble-ai.databaseUrl" -}}
{{- if .Values.mysql.enabled -}}
mysql+pymysql://{{ .Values.mysql.user }}:{{ .Values.mysql.password }}@{{ include "devtrouble-ai.fullname" . }}-mysql:3306/{{ .Values.mysql.database }}
{{- else -}}
{{ required "mysql.enabled=false면 secrets.databaseUrl(RDS 등 외부 DB 접속 문자열)이 필요합니다" .Values.secrets.databaseUrl }}
{{- end -}}
{{- end }}

{{- define "devtrouble-ai.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ include "devtrouble-ai.fullname" . }}-redis:6379/0
{{- else -}}
{{ required "redis.enabled=false면 secrets.redisUrl(ElastiCache 등 외부 Redis 접속 문자열)이 필요합니다" .Values.secrets.redisUrl }}
{{- end -}}
{{- end }}

{{- define "devtrouble-ai.celeryBrokerUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ include "devtrouble-ai.fullname" . }}-redis:6379/1
{{- else -}}
{{ required "redis.enabled=false면 secrets.celeryBrokerUrl이 필요합니다" .Values.secrets.celeryBrokerUrl }}
{{- end -}}
{{- end }}

{{- define "devtrouble-ai.celeryResultBackendUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ include "devtrouble-ai.fullname" . }}-redis:6379/2
{{- else -}}
{{ required "redis.enabled=false면 secrets.celeryResultBackendUrl이 필요합니다" .Values.secrets.celeryResultBackendUrl }}
{{- end -}}
{{- end }}

{{- define "devtrouble-ai.qdrantUrl" -}}
{{- if .Values.qdrant.enabled -}}
http://{{ include "devtrouble-ai.fullname" . }}-qdrant:6333
{{- else -}}
{{ .Values.secrets.qdrantUrl }}
{{- end -}}
{{- end }}
