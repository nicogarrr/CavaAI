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
        from: `"JLCavaAI" <noreply@jlcavaai.com>`,
        to: email,
        subject: `Bienvenido a JLCavaAI - tu herramienta de análisis de inversiones`,
        text: 'Gracias por unirte a JLCavaAI',
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
        from: `"JLCavaAI" <noreply@jlcavaai.com>`,
        to: email,
        subject: `📈 Resumen de Noticias de Mercado - ${date}`,
        text: `Resumen diario de noticias de mercado de JLCavaAI`,
        html: htmlTemplate,
    };

    await transporter.sendMail(mailOptions);
};