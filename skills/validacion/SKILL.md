---
name: validacion-historica
description: Evaluar el riesgo mediante cohortes temporales y distinguir demostración de validación con históricos autorizados.
---
Usa scripts/validate_history.py con un Excel o CSV seleccionado explícitamente por el operador y un protocolo. No busques datos personales ni inventes un histórico real.

El protocolo declara la definición de deserción, horizonte, momento de observación y significado de matrícula y pagos. El ejemplo histórico debe completarse y la autorización confirmarse. Son declaraciones del responsable: no constituyen una verificación independiente ni autorización institucional otorgada por el programa.

Evalúa cada cohorte con el pasado; la imputación, escalado y entrenamiento no deben usar la cohorte de evaluación. Reporta prevalencia, average precision, ROC AUC, Brier, precisión, sensibilidad y calibración. Si hay grupos, conserva mínimos de filas y distingue resultados no evaluables. No elimines cohortes fallidas para presentar solo resultados favorables; la última debe ser evaluable.

No presentes datos sintéticos como validación real. No afirmes eficacia institucional ni ausencia de fuga de información solo por dividir periodos. El LLM no recibe filas ni decide etiquetas o probabilidades. Guarda un informe nuevo sin sobrescribir otros y registra las limitaciones. Las decisiones de intervención siguen requiriendo revisión humana.
