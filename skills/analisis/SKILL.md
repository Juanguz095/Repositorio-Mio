---
name: analisis-desercion
description: Entrenar y evaluar un modelo temporal de riesgo mediante código.
---
Confirma definición de deserción y fecha de observación antes de usar datos reales. Para la demo usa synthetic. Usa clean y train del pipeline, nunca estimaciones del LLM. La última cohorte se reserva para evaluación. La imputación se ajusta únicamente con datos de entrenamiento. Reporta average precision, Brier, precisión y sensibilidad a 0.5; ese umbral es demostrativo. No presentes métricas sintéticas como evidencia clínica o institucional. La aprobación humana se ejecuta en la API con credencial de revisor; el agente no debe recibir esa credencial.

Para evaluación histórica reutilizable consulta skills/validacion/SKILL.md y scripts/validate_history.py. No uses matrícula futura ni obligaciones de pago no aplicables como predictores. Reporta las variables no disponibles; no inventes observaciones para completar columnas.
