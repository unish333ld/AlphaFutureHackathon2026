import { useRef, useState } from "react";
import { Button, Dialog, Input, Notice } from "../shared/ui/kit";
import { LinkButton } from "../shared/ui/navigation";
import s from "../app/layout.module.css";

export default function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <div className={s.assistantButton}>
        <Button
          ref={trigger}
          size={40}
          view="outlined"
          onClick={() => setOpen(true)}
          aria-expanded={open}
        >
          Помощник · демо
        </Button>
      </div>
      <Dialog
        title="Помощник"
        returnFocusRef={trigger}
        open={open}
        onClose={() => setOpen(false)}
        footer={<Button onClick={() => setOpen(false)}>Закрыть</Button>}
      >
        <Notice title="Демонстрационный режим">
          Это визуальная заготовка. ИИ не подключён, сообщения не отправляются и
          кредитные решения не объясняются моделью.
        </Notice>
        <Input
          label="Вопрос помощнику"
          labelView="outer"
          placeholder="Чат пока не подключён"
          block
          disabled
        />
        <div onClick={() => setOpen(false)}>
          <LinkButton to="/app/loans">Открыть заявки</LinkButton>
        </div>
      </Dialog>
    </>
  );
}
