import nodemailer from 'nodemailer';
import {WELCOME_EMAIL_TEMPLATE, NEWS_SUMMARY_EMAIL_TEMPLATE} from "@/lib/nodemailer/templates";

export const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.NODEMAILER_EMAIL!,
        pass: process.env.NODEMAILER_PASSWORD!,
    }
})

export const sendWelcomeEmail = async ({ email, name, intro }: WelcomeEmailData) => {
    const htmlTemplate = WELCOME_EMAIL_TEMPLATE
        .replace('{{name}}', name)
        .replace('{{intro}}', intro);

    const mailOptions = {
        from: `"CavaAI" <${process.env.NODEMAILER_EMAIL || 'noreply@cavaai.local'}>`,
        to: email,
        subject: `Bienvenido a CavaAI - tu herramienta de análisis de inversiones`,
        text: 'Gracias por unirte a CavaAI',
        html: htmlTemplate,
    }

    await transporter.sendMail(mailOptions);
}

export const sendNewsSummaryEmail = async (
    { email, date, newsContent }: { email: string; date: string; newsContent: string }
): Promise<void> => {
    const htmlTemplate = NEWS_SUMMARY_EMAIL_TEMPLATE
        .replace('{{date}}', date)
        .replace('{{newsContent}}', newsContent);

    const mailOptions = {
        from: `"CavaAI" <${process.env.NODEMAILER_EMAIL || 'noreply@cavaai.local'}>`,
        to: email,
        subject: `📈 Resumen de Noticias de Mercado - ${date}`,
        text: `Resumen diario de noticias de mercado de CavaAI`,
        html: htmlTemplate,
    };

    await transporter.sendMail(mailOptions);
};
