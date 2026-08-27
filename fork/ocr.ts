/*
 * OCR prefill — scan an act inside OpenCRVS instead of typing it.
 *
 * Deployed into the countryconfig fork as src/form/v2/ocr.ts (see
 * tools/deploy_fork_ocr.sh). Mirrors the MOSIP id-reader pattern in
 * mosip.ts: a small cluster of fields on a declare page fetches data from
 * an external service, and the ordinary form fields read their value out
 * of that fetch result.
 *
 * Two ways in, one result:
 *
 *   upload  child.ocr-scan (FILE) -> OpenCRVS stores the scan in its own
 *           MinIO exactly like documents.proofOfBirth does -> that upload
 *           triggers child.ocr-fetch (HTTP), which POSTs the resulting
 *           MinIO path to the OCR service. FieldType.HTTP can only send
 *           JSON, never file bytes, which is why the path travels rather
 *           than the file.
 *
 *   phone   child.ocr-qr shows a QR pointing at the OCR service's mobile
 *           capture page. After shooting the act the registrar presses
 *           child.ocr-phone-btn, which triggers child.ocr-phone-fetch
 *           (HTTP) to collect the freshly analysed capture.
 *
 * Both answer with declaration values already keyed by V2 field ids, so
 * every prefilled field just reads its own value through `value:` and the
 * registrar continues to OpenCRVS's own review page as usual.
 */

import {
  ConditionalType,
  FieldConfigInput,
  FieldType,
  field,
  never,
  not
} from '@opencrvs/toolkit/events'
import { OCR_PREFILL_URL } from '@countryconfig/constants'

const UPLOAD_FETCH = 'child.ocr-fetch'
const PHONE_FETCH = 'child.ocr-phone-fetch'

/**
 * Reads one prefilled value out of whichever OCR fetch produced it.
 *
 * Attach to a field as `value: ocrValue('child.dob')`. The first truthy
 * reference wins, so the upload and the phone capture can coexist. The
 * field stays fully editable — this only supplies a value when the OCR
 * produced one, and the registrar can overwrite anything it got wrong.
 */
export const ocrParent = () => [field(UPLOAD_FETCH), field(PHONE_FETCH)]

/**
 * Marks a field as listening to the OCR fetches.
 *
 * `value` alone is inert: the client builds its listener map from `parent`
 * (getParentsOfListenerFields) and only re-resolves `value` when a declared
 * parent changes. Every OCR-filled field therefore needs both.
 */
export const ocrValue = (fieldId: string) => [
  field(UPLOAD_FETCH).get(`data.fields.${fieldId}`),
  field(PHONE_FETCH).get(`data.fields.${fieldId}`)
]

/**
 * The scan panel. Returned fields are appended to the child page.
 *
 * Kept off the review page (DISPLAY_ON_REVIEW: never) — the scan itself is
 * attached as a supporting document, and the machinery that produced the
 * values is not something a registrar needs to re-read.
 */
export const getOcrPrefillFields = (): FieldConfigInput[] => {
  const hiddenOnReview = {
    type: ConditionalType.DISPLAY_ON_REVIEW,
    conditional: never()
  }

  return [
    {
      id: 'child.ocr-divider',
      type: FieldType.DIVIDER,
      label: {
        defaultMessage: '',
        description: 'Divider above the OCR prefill panel',
        id: 'event.birth.action.declare.form.section.child.field.ocr.divider'
      },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-title',
      type: FieldType.PARAGRAPH,
      label: {
        defaultMessage: 'Pré-remplir depuis un acte scanné',
        description: 'Title of the OCR prefill panel',
        id: 'event.birth.action.declare.form.section.child.field.ocr.title'
      },
      configuration: { styles: { fontVariant: 'h4' } },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-intro',
      type: FieldType.PARAGRAPH,
      label: {
        defaultMessage:
          "Déposez une photo ou un PDF de l'acte ci-dessous, ou ouvrez le " +
          'site OCR sur un téléphone pour le photographier. Les champs du ' +
          'formulaire se remplissent automatiquement : vérifiez-les ensuite ' +
          'sur la page de relecture.',
        description: 'Intro text of the OCR prefill panel',
        id: 'event.birth.action.declare.form.section.child.field.ocr.intro'
      },
      configuration: { styles: { fontVariant: 'reg16', hint: true } },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-scan',
      type: FieldType.FILE,
      required: false,
      label: {
        defaultMessage: "Acte de naissance scanné",
        description: 'Label for the OCR scan upload field',
        id: 'event.birth.action.declare.form.section.child.field.ocr.scan'
      },
      configuration: {
        style: { width: 'full' },
        fileName: {
          defaultMessage: 'Acte scanné',
          description: 'File name shown for the uploaded scan',
          id: 'event.birth.action.declare.form.section.child.field.ocr.scan.fileName'
        }
      },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-fetch',
      type: FieldType.HTTP,
      label: {
        defaultMessage: "Analyse OCR de l'acte",
        description: 'Label of the OCR upload fetch field (never displayed)',
        id: 'event.birth.action.declare.form.section.child.field.ocr.fetch'
      },
      conditionals: [hiddenOnReview],
      configuration: {
        trigger: field('child.ocr-scan'),
        url: `${OCR_PREFILL_URL}/api/opencrvs/analyze`,
        method: 'POST',
        // a full page takes ~40-90s to OCR; stay above the service's own
        // 110s cap so a slow page still lands instead of aborting here
        timeout: 120000,
        headers: { 'Content-Type': 'application/json' },
        body: { path: field('child.ocr-scan').get('path') },
        errorValue: { declaration: {} }
      }
    },
    {
      id: 'child.ocr-qr-link',
      type: FieldType.LINK_BUTTON,
      label: {
        defaultMessage: "Photographier l'acte avec un téléphone",
        description: 'Opens the OCR site, which shows a QR to scan',
        id: 'event.birth.action.declare.form.section.child.field.ocr.qrLink'
      },
      configuration: {
        icon: 'QrCode',
        url: OCR_PREFILL_URL,
        text: {
          defaultMessage: "Photographier l'acte avec un téléphone",
          description: 'Text of the link opening the OCR site QR page',
          id: 'event.birth.action.declare.form.section.child.field.ocr.qrLinkText'
        }
      },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-phone-btn',
      type: FieldType.BUTTON,
      label: {
        defaultMessage: "J'ai photographié l'acte",
        description: 'Button that collects the phone capture',
        id: 'event.birth.action.declare.form.section.child.field.ocr.phoneBtn'
      },
      configuration: {
        icon: 'QrCode',
        text: {
          defaultMessage: "J'ai photographié l'acte",
          description: 'Text of the phone-capture button',
          id: 'event.birth.action.declare.form.section.child.field.ocr.phoneBtnText'
        }
      },
      conditionals: [hiddenOnReview]
    },
    {
      id: 'child.ocr-phone-fetch',
      type: FieldType.HTTP,
      label: {
        defaultMessage: 'Récupération de la photo',
        description: 'Label of the OCR phone fetch field (never displayed)',
        id: 'event.birth.action.declare.form.section.child.field.ocr.phoneFetch'
      },
      conditionals: [hiddenOnReview],
      configuration: {
        trigger: field('child.ocr-phone-btn'),
        url: `${OCR_PREFILL_URL}/api/opencrvs/analyze/phone/latest`,
        method: 'GET',
        timeout: 120000,
        errorValue: { declaration: {} }
      }
    },
    {
      id: 'child.ocr-loader',
      type: FieldType.LOADER,
      parent: [field(UPLOAD_FETCH), field(PHONE_FETCH)],
      label: {
        defaultMessage: "Analyse de l'acte en cours…",
        description: 'Loader shown while the OCR runs',
        id: 'event.birth.action.declare.form.section.child.field.ocr.loader'
      },
      conditionals: [
        {
          type: ConditionalType.SHOW,
          conditional: not(
            field(UPLOAD_FETCH)
              .get('loading')
              .isFalsy()
          )
        },
        hiddenOnReview
      ],
      configuration: {
        text: {
          defaultMessage:
            "Analyse de l'acte en cours — les champs vont se remplir…",
          description: 'Loader text shown while the OCR runs',
          id: 'event.birth.action.declare.form.section.child.field.ocr.loaderText'
        }
      }
    }
  ]
}
